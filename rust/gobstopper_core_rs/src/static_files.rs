use pyo3::prelude::*;
use pyo3::types::PyBytes;
use std::collections::HashMap;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::{Arc, RwLock};
use std::time::{SystemTime, UNIX_EPOCH};
use std::sync::atomic::{AtomicU64, Ordering};
use once_cell::sync::Lazy;
use httpdate::{fmt_http_date, parse_http_date};
use sha2::{Sha256, Digest};

#[pyclass]
pub struct StaticHandler {
    root_path: PathBuf,
    cache: Arc<RwLock<HashMap<String, CachedFile>>>,
    max_cache_size: usize,
    cache_size: Arc<RwLock<usize>>,
}

struct CachedFile {
    content: Vec<u8>,
    content_type: String,
    etag: String,
    #[allow(dead_code)]
    last_modified: u64,
}

static STATIC_BYTES_TOTAL: Lazy<AtomicU64> = Lazy::new(|| AtomicU64::new(0));
static STATIC_REQUESTS_TOTAL: Lazy<AtomicU64> = Lazy::new(|| AtomicU64::new(0));
static STATIC_304_TOTAL: Lazy<AtomicU64> = Lazy::new(|| AtomicU64::new(0));
static STATIC_206_TOTAL: Lazy<AtomicU64> = Lazy::new(|| AtomicU64::new(0));
static STATIC_COMPRESSED_BYTES_TOTAL: Lazy<AtomicU64> = Lazy::new(|| AtomicU64::new(0));
static STATIC_UNCOMPRESSED_BYTES_TOTAL: Lazy<AtomicU64> = Lazy::new(|| AtomicU64::new(0));

#[pymethods]
impl StaticHandler {
    #[new]
    pub fn new(root_path: &str) -> Self {
        StaticHandler {
            root_path: PathBuf::from(root_path),
            cache: Arc::new(RwLock::new(HashMap::new())),
            max_cache_size: 50 * 1024 * 1024, // 50MB cache
            cache_size: Arc::new(RwLock::new(0)),
        }
    }

    #[pyo3(signature = (path, if_none_match=None))]
    pub fn serve<'py>(&self, py: Python<'py>, path: &str, if_none_match: Option<&str>) -> PyResult<Option<(Bound<'py, PyBytes>, String, String, u16)>> {
        // Security: prevent directory traversal
        if path.contains("..") {
            return Ok(None);
        }

        // Check cache first
        {
            let cache = self.cache.read().unwrap();
            if let Some(cached) = cache.get(path) {
                // Check ETag for 304 Not Modified
                if let Some(client_etag) = if_none_match {
                    if client_etag == cached.etag {
                        return Ok(Some((
                            PyBytes::new_bound(py, &[]),
                            cached.content_type.clone(),
                            cached.etag.clone(),
                            304, // Not Modified
                        )));
                    }
                }
                
                return Ok(Some((
                    PyBytes::new_bound(py, &cached.content),
                    cached.content_type.clone(),
                    cached.etag.clone(),
                    200,
                )));
            }
        }

        // Build full path
        let full_path = self.root_path.join(path.trim_start_matches('/'));
        
        // Check if file exists
        if !full_path.exists() || !full_path.is_file() {
            return Ok(None);
        }
        
        // Read file
        let mut file = fs::File::open(&full_path).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyIOError, _>(format!("Failed to open file: {}", e))
        })?;
        
        let metadata = file.metadata().map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyIOError, _>(format!("Failed to get metadata: {}", e))
        })?;
        
        let file_size = metadata.len() as usize;
        
        // Only cache files under 10MB
        if file_size < 10_485_760 {
            let mut content = Vec::new();
            file.read_to_end(&mut content).map_err(|e| {
                PyErr::new::<pyo3::exceptions::PyIOError, _>(format!("Failed to read file: {}", e))
            })?;
            
            let content_type = mime_type_from_path(&full_path);
            let etag = generate_etag(&content);
            let last_modified = metadata
                .modified()
                .unwrap_or(SystemTime::now())
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs();
            
            // Check if we have room in cache
            let current_size = *self.cache_size.read().unwrap();
            if current_size + file_size < self.max_cache_size {
                // Cache it
                let cached = CachedFile {
                    content: content.clone(),
                    content_type: content_type.clone(),
                    etag: etag.clone(),
                    last_modified,
                };
                
                let mut cache = self.cache.write().unwrap();
                cache.insert(path.to_string(), cached);
                
                // Update cache size
                let mut size = self.cache_size.write().unwrap();
                *size += file_size;
            }
            
            // Check ETag
            if let Some(client_etag) = if_none_match {
                if client_etag == etag {
                    return Ok(Some((
                        PyBytes::new_bound(py, &[]),
                        content_type,
                        etag,
                        304,
                    )));
                }
            }
            
            Ok(Some((
                PyBytes::new_bound(py, &content),
                content_type,
                etag,
                200,
            )))
        } else {
            // For large files, stream directly without caching
            let mut content = Vec::new();
            file.read_to_end(&mut content).map_err(|e| {
                PyErr::new::<pyo3::exceptions::PyIOError, _>(format!("Failed to read large file: {}", e))
            })?;
            
            let content_type = mime_type_from_path(&full_path);
            let etag = format!("{}-{}", 
                metadata.len(), 
                metadata.modified()
                    .unwrap_or(SystemTime::now())
                    .duration_since(UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_secs()
            );
            
            // Check ETag
            if let Some(client_etag) = if_none_match {
                if client_etag == etag {
                    return Ok(Some((
                        PyBytes::new_bound(py, &[]),
                        content_type,
                        etag,
                        304,
                    )));
                }
            }
            
            Ok(Some((
                PyBytes::new_bound(py, &content),
                content_type,
                etag,
                200,
            )))
        }
    }

    #[pyo3(signature = (path, if_none_match=None, if_modified_since=None, range_header=None, if_range=None, accept_encoding=None, index=false))]
    pub fn serve_adv<'py>(
        &self,
        py: Python<'py>,
        path: &str,
        if_none_match: Option<&str>,
        if_modified_since: Option<&str>,
        range_header: Option<&str>,
        if_range: Option<&str>,
        accept_encoding: Option<&str>,
        index: bool,
    ) -> PyResult<Option<(Bound<'py, PyBytes>, HashMap<String, String>, u16)>> {
        STATIC_REQUESTS_TOTAL.fetch_add(1, Ordering::Relaxed);

        let mut req_path = path;
        if req_path.contains("..") {
            return Ok(None);
        }
        if req_path.is_empty() || req_path == "/" {
            if index { req_path = "/index.html"; } else { return Ok(None); }
        }

        // Canonicalize path
        let rel = req_path.trim_start_matches('/');
        let mut base_path = self.root_path.join(rel);
        // If directory and index requested
        if base_path.is_dir() {
            if index { base_path = base_path.join("index.html"); } else { return Ok(None); }
        }

        // Accept-Encoding negotiation for precompressed assets
        let mut encoding: Option<&str> = None;
        if let Some(ae) = accept_encoding {
            if base_path.exists() == false {
                // nothing to do
            }
            // Prefer br then gzip if corresponding files exist
            if ae.contains("br") {
                let p = PathBuf::from(format!("{}{}.br", base_path.display(), ""));
                if p.exists() { base_path = p; encoding = Some("br"); }
            }
            if encoding.is_none() && ae.contains("gzip") {
                let p = PathBuf::from(format!("{}{}.gz", base_path.display(), ""));
                if p.exists() { base_path = p; encoding = Some("gzip"); }
            }
        }

        if !base_path.exists() || !base_path.is_file() {
            return Ok(None);
        }

        let mut file = fs::File::open(&base_path).map_err(|e| PyErr::new::<pyo3::exceptions::PyIOError,_>(format!("Failed to open: {}", e)))?;
        let metadata = file.metadata().map_err(|e| PyErr::new::<pyo3::exceptions::PyIOError,_>(format!("Failed to stat: {}", e)))?;
        let mtime = metadata.modified().unwrap_or(SystemTime::now());
        let lm_http = fmt_http_date(mtime);
        let file_size = metadata.len() as usize;

        // Determine original content-type (without .br/.gz)
        let content_type = {
            let mut orig = base_path.clone();
            if let Some(ext) = orig.extension().and_then(|s| s.to_str()) {
                if ext == "br" || ext == "gz" {
                    orig.set_extension(""); // remove extension entirely; next guess
                }
            }
            // If we removed ext, path like file.css., fix to remove trailing dot
            let ct = mime_type_from_path(if orig.extension().is_none() { &orig } else { &orig });
            ct
        };

        // Read content
        let mut content = Vec::new();
        file.read_to_end(&mut content).map_err(|e| PyErr::new::<pyo3::exceptions::PyIOError,_>(format!("Failed to read: {}", e)))?;

        // ETag
        let etag = if file_size < 8 * 1024 * 1024 { // strong for small
            generate_strong_etag(&content)
        } else {
            generate_weak_etag(metadata.len(), mtime)
        };

        // Conditional GET checks
        if let Some(tag) = if_none_match {
            if tag == etag {
                STATIC_304_TOTAL.fetch_add(1, Ordering::Relaxed);
                let mut headers = HashMap::new();
                headers.insert("etag".to_string(), etag);
                headers.insert("last-modified".to_string(), lm_http.clone());
                headers.insert("cache-control".to_string(), cache_policy_for(rel));
                if encoding.is_some() { headers.insert("vary".to_string(), "Accept-Encoding".to_string()); }
                return Ok(Some((PyBytes::new_bound(py, &[]), headers, 304)));
            }
        }
        if let Some(since) = if_modified_since {
            if let Ok(since_time) = parse_http_date(since) {
                if mtime <= since_time {
                    STATIC_304_TOTAL.fetch_add(1, Ordering::Relaxed);
                    let mut headers = HashMap::new();
                    headers.insert("etag".to_string(), etag.clone());
                    headers.insert("last-modified".to_string(), lm_http.clone());
                    headers.insert("cache-control".to_string(), cache_policy_for(rel));
                    if encoding.is_some() { headers.insert("vary".to_string(), "Accept-Encoding".to_string()); }
                    return Ok(Some((PyBytes::new_bound(py, &[]), headers, 304)));
                }
            }
        }

        // Range handling (single range)
        let mut status: u16 = 200;
        let mut headers = HashMap::new();
        let total_len = content.len() as u64;
        let mut body_slice: &[u8] = &content;
        if let Some(rh) = range_header {
            if rh.starts_with("bytes=") {
                // If-Range validation
                let mut apply_range = true;
                if let Some(ir) = if_range {
                    if ir.starts_with('"') {
                        apply_range = (ir == etag);
                    } else if let Ok(ir_time) = parse_http_date(ir) {
                        apply_range = mtime <= ir_time;
                    }
                }
                if apply_range {
                    if let Some((start, end)) = parse_single_range(&rh[6..], total_len) {
                        let s = start as usize; let e = end as usize; // inclusive end
                        if s <= e && e < content.len() {
                            status = 206;
                            body_slice = &content[s..=e];
                            headers.insert("content-range".to_string(), format!("bytes {}-{}/{}", start, end, total_len));
                            STATIC_206_TOTAL.fetch_add(1, Ordering::Relaxed);
                        } else {
                            // invalid -> 416
                            let mut h = HashMap::new();
                            h.insert("content-range".to_string(), format!("*/{}", total_len));
                            return Ok(Some((PyBytes::new_bound(py, &[]), h, 416)));
                        }
                    } else {
                        let mut h = HashMap::new();
                        h.insert("content-range".to_string(), format!("*/{}", total_len));
                        return Ok(Some((PyBytes::new_bound(py, &[]), h, 416)));
                    }
                }
            }
        }

        // Metrics
        STATIC_BYTES_TOTAL.fetch_add(body_slice.len() as u64, Ordering::Relaxed);
        if let Some(enc) = encoding {
            headers.insert("content-encoding".to_string(), enc.to_string());
            headers.insert("vary".to_string(), "Accept-Encoding".to_string());
            STATIC_COMPRESSED_BYTES_TOTAL.fetch_add(body_slice.len() as u64, Ordering::Relaxed);
        } else {
            STATIC_UNCOMPRESSED_BYTES_TOTAL.fetch_add(body_slice.len() as u64, Ordering::Relaxed);
        }

        headers.insert("content-type".to_string(), content_type.clone());
        headers.insert("etag".to_string(), etag.clone());
        headers.insert("last-modified".to_string(), lm_http.clone());
        headers.insert("cache-control".to_string(), cache_policy_for(rel));
        headers.insert("content-length".to_string(), format!("{}", body_slice.len()));

        Ok(Some((PyBytes::new_bound(py, body_slice), headers, status)))
    }
    
    pub fn clear_cache(&self) {
        let mut cache = self.cache.write().unwrap();
        cache.clear();
        let mut size = self.cache_size.write().unwrap();
        *size = 0;
    }

    pub fn metrics(&self) -> HashMap<String, f64> {
        let bytes = STATIC_BYTES_TOTAL.load(Ordering::Relaxed) as f64;
        let reqs = STATIC_REQUESTS_TOTAL.load(Ordering::Relaxed) as f64;
        let m304 = STATIC_304_TOTAL.load(Ordering::Relaxed) as f64;
        let m206 = STATIC_206_TOTAL.load(Ordering::Relaxed) as f64;
        let comp = STATIC_COMPRESSED_BYTES_TOTAL.load(Ordering::Relaxed) as f64;
        let uncomp = STATIC_UNCOMPRESSED_BYTES_TOTAL.load(Ordering::Relaxed) as f64;
        let ratio = if (comp + uncomp) > 0.0 { (uncomp.max(1.0)) / (comp + uncomp) } else { 1.0 };
        let mut m = HashMap::new();
        m.insert("static_bytes_total".to_string(), bytes);
        m.insert("static_requests_total".to_string(), reqs);
        m.insert("static_304_total".to_string(), m304);
        m.insert("static_206_total".to_string(), m206);
        m.insert("static_compression_ratio".to_string(), ratio);
        m
    }
}

fn mime_type_from_path(path: &Path) -> String {
    match path.extension().and_then(|s| s.to_str()) {
        Some("html") => "text/html; charset=utf-8",
        Some("css") => "text/css; charset=utf-8",
        Some("js") | Some("mjs") => "application/javascript; charset=utf-8",
        Some("json") => "application/json",
        Some("png") => "image/png",
        Some("jpg") | Some("jpeg") => "image/jpeg",
        Some("gif") => "image/gif",
        Some("svg") => "image/svg+xml",
        Some("ico") => "image/x-icon",
        Some("webp") => "image/webp",
        Some("avif") => "image/avif",
        Some("woff") => "font/woff",
        Some("woff2") => "font/woff2",
        Some("ttf") => "font/ttf",
        Some("eot") => "application/vnd.ms-fontobject",
        Some("pdf") => "application/pdf",
        Some("zip") => "application/zip",
        Some("tar") => "application/x-tar",
        Some("gz") => "application/gzip",
        Some("mp4") => "video/mp4",
        Some("webm") => "video/webm",
        Some("mp3") => "audio/mpeg",
        Some("wav") => "audio/wav",
        Some("ogg") => "audio/ogg",
        Some("txt") => "text/plain; charset=utf-8",
        Some("xml") => "text/xml; charset=utf-8",
        Some("md") => "text/markdown; charset=utf-8",
        _ => "application/octet-stream",
    }
    .to_string()
}

fn generate_etag(_content: &[u8]) -> String {
    // deprecated by generate_strong_etag; keep for compatibility if needed
    "\"deprecated\"".to_string()
}

fn generate_strong_etag(content: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(content);
    let hash = hasher.finalize();
    format!("\"{}\"", hex::encode(hash))
}

fn generate_weak_etag(size: u64, mtime: SystemTime) -> String {
    let secs = mtime.duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
    format!("W/\"{}-{}\"", size, secs)
}

fn is_fingerprinted(path: &str) -> bool {
    // simple check for .[a-f0-9]{8,}
    let bytes = path.as_bytes();
    for i in 0..bytes.len() {
        if bytes[i] == b'.' {
            // count hex
            let mut j = i + 1;
            let mut count = 0;
            while j < bytes.len() {
                let c = bytes[j];
                let is_hex = (c >= b'0' && c <= b'9') || (c >= b'a' && c <= b'f');
                if !is_hex { break; }
                count += 1; j += 1;
            }
            if count >= 8 { return true; }
        }
    }
    false
}

fn cache_policy_for(rel: &str) -> String {
    if is_fingerprinted(rel) {
        "public, max-age=31536000, immutable".to_string()
    } else {
        "public, max-age=3600".to_string()
    }
}

fn parse_single_range(spec: &str, total: u64) -> Option<(u64,u64)> {
    // spec like start-end, -suffix, start-
    let parts: Vec<&str> = spec.split(',').collect();
    if parts.len() != 1 { return None; }
    let s = parts[0].trim();
    let mut split = s.splitn(2, '-');
    let a = split.next()?; let b = split.next()?;
    if a.is_empty() {
        // suffix bytes: last b bytes
        let n: u64 = b.parse().ok()?;
        if n == 0 { return None; }
        let start = if n > total { 0 } else { total - n };
        return Some((start, total.saturating_sub(1)));
    } else {
        let start: u64 = a.parse().ok()?;
        if b.is_empty() {
            if start >= total { return None; }
            return Some((start, total - 1));
        } else {
            let end: u64 = b.parse().ok()?;
            if start > end { return None; }
            if end >= total { return None; }
            return Some((start, end));
        }
    }
}
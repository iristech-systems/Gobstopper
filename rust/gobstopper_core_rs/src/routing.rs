use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::collections::HashMap;
use regex::Regex;
use percent_encoding::percent_decode_str;

// Converter types for typed path parameters
#[derive(Clone, Debug)]
enum Converter {
    String,
    Int,
    Uuid,
    Date,
    Path,  // tail wildcard that consumes rest of path
}

impl Converter {
    fn regex(&self) -> &'static str {
        match self {
            Converter::String => r"[^/]+",
            Converter::Int => r"-?\d+",
            Converter::Uuid => r"(?i)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            Converter::Date => r"\d{4}-\d{2}-\d{2}",
            Converter::Path => r".+",
        }
    }

    fn validate(&self, value: &str) -> bool {
        match self {
            Converter::String => true,
            Converter::Int => value.parse::<i64>().is_ok(),
            Converter::Uuid => {
                // Simple validation - just check format
                let re = Regex::new(r"(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$").unwrap();
                re.is_match(value)
            }
            Converter::Date => {
                // Validate YYYY-MM-DD format
                let re = Regex::new(r"^\d{4}-\d{2}-\d{2}$").unwrap();
                re.is_match(value)
            }
            Converter::Path => true,
        }
    }

    fn from_name(name: &str) -> Self {
        match name {
            "int" => Converter::Int,
            "uuid" => Converter::Uuid,
            "date" => Converter::Date,
            "path" => Converter::Path,
            _ => Converter::String,
        }
    }
}

// Trailing slash policy
#[pyclass(eq, eq_int)]
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum SlashPolicy {
    Strict,           // Exact match required
    RedirectToSlash,  // Redirect /foo to /foo/
    RedirectToNoSlash, // Redirect /foo/ to /foo
}

#[pymethods]
impl SlashPolicy {
    #[new]
    fn new() -> Self {
        SlashPolicy::Strict
    }
}

// Route conflict types
#[pyclass]
#[derive(Clone)]
pub struct RouteConflict {
    #[pyo3(get)]
    pub conflict_type: String,
    #[pyo3(get)]
    pub pattern: String,
    #[pyo3(get)]
    pub method: String,
    #[pyo3(get)]
    pub existing_pattern: Option<String>,
    #[pyo3(get)]
    pub reason: String,
}

#[pymethods]
impl RouteConflict {
    fn __repr__(&self) -> String {
        format!("RouteConflict({}: {} [{}] - {})",
            self.conflict_type, self.pattern, self.method, self.reason)
    }
}

// Router statistics
#[pyclass]
#[derive(Clone)]
pub struct RouterStats {
    #[pyo3(get)]
    pub routes: usize,
    #[pyo3(get)]
    pub dynamic_segments: usize,
    #[pyo3(get)]
    pub nodes: usize,
    #[pyo3(get)]
    pub max_depth: usize,
}

impl RouterStats {
    fn new() -> Self {
        RouterStats {
            routes: 0,
            dynamic_segments: 0,
            nodes: 0,
            max_depth: 0
        }
    }
}

// Pattern segment - represents one segment in a route pattern
#[derive(Clone, Debug)]
struct PatternSegment {
    is_dynamic: bool,
    name: Option<String>,
    converter: Converter,
    literal: String,
}

// Route information stored at terminal nodes
struct RouteInfo {
    handler: PyObject,
    pattern: String,
    method: String,
    segments: Vec<PatternSegment>,
    name: Option<String>,  // For reverse routing
}

// Trie node for routing
struct Node {
    // Static children (exact matches)
    children: HashMap<String, Node>,
    // Dynamic child (parameter segment)
    dynamic_child: Option<Box<Node>>,
    // Routes at this node (keyed by method)
    routes: HashMap<String, RouteInfo>,
}

impl Node {
    fn new() -> Self {
        Node {
            children: HashMap::new(),
            dynamic_child: None,
            routes: HashMap::new(),
        }
    }

    fn match_path<'a>(
        &'a self,
        segments: &[&str],
        params: &mut HashMap<String, String>,
        segment_specs: &[PatternSegment],
        spec_offset: usize,
    ) -> Option<&'a Node> {
        if segments.is_empty() {
            return Some(self);
        }

        let segment = segments[0];
        let remaining = &segments[1..];

        // Try static match first
        if let Some(child) = self.children.get(segment) {
            return child.match_path(remaining, params, segment_specs, spec_offset);
        }

        // Try dynamic match
        if let Some(ref child) = self.dynamic_child {
            if spec_offset < segment_specs.len() {
                let spec = &segment_specs[spec_offset];
                if spec.is_dynamic {
                    // Validate converter
                    if spec.converter.validate(segment) {
                        if let Some(ref name) = spec.name {
                            params.insert(name.clone(), segment.to_string());
                        }
                        return child.match_path(remaining, params, segment_specs, spec_offset + 1);
                    }
                }
            }
        }

        None
    }

    fn accumulate_stats(&self, depth: usize, stats: &mut RouterStats) {
        stats.nodes += 1;
        if depth > stats.max_depth {
            stats.max_depth = depth;
        }
        stats.routes += self.routes.len();
        if self.dynamic_child.is_some() {
            stats.dynamic_segments += 1;
        }

        for child in self.children.values() {
            child.accumulate_stats(depth + 1, stats);
        }
        if let Some(ref child) = self.dynamic_child {
            child.accumulate_stats(depth + 1, stats);
        }
    }
}

// Main router
#[pyclass]
pub struct Router {
    root: Node,
    slash_policy: SlashPolicy,
    conflicts: Vec<RouteConflict>,
    // For reverse routing: name -> (pattern, method)
    named_routes: HashMap<String, (String, String)>,
}

#[pymethods]
impl Router {
    #[new]
    #[pyo3(signature = (slash_policy=None))]
    pub fn new(slash_policy: Option<SlashPolicy>) -> Self {
        Router {
            root: Node::new(),
            slash_policy: slash_policy.unwrap_or(SlashPolicy::Strict),
            conflicts: Vec::new(),
            named_routes: HashMap::new(),
        }
    }

    pub fn set_slash_policy(&mut self, policy: SlashPolicy) {
        self.slash_policy = policy;
    }

    #[pyo3(signature = (path, method, value, name=None))]
    pub fn insert(
        &mut self,
        path: &str,
        method: &str,
        value: PyObject,
        name: Option<String>,
    ) -> PyResult<()> {
        let segments = self.parse_pattern(path)?;
        let method = method.to_uppercase();

        // Check for conflicts
        self.detect_conflicts(path, &method, &segments);

        // Insert into trie
        let mut current = &mut self.root;

        for segment in &segments {
            if segment.is_dynamic {
                if current.dynamic_child.is_none() {
                    current.dynamic_child = Some(Box::new(Node::new()));
                }
                current = current.dynamic_child.as_mut().unwrap();
            } else {
                current = current.children
                    .entry(segment.literal.clone())
                    .or_insert_with(Node::new);
            }
        }

        // Store route info
        let route_info = RouteInfo {
            handler: value,
            pattern: path.to_string(),
            method: method.clone(),
            segments: segments.clone(),
            name: name.clone(),
        };

        // Check for duplicate
        if current.routes.contains_key(&method) {
            self.conflicts.push(RouteConflict {
                conflict_type: "duplicate".to_string(),
                pattern: path.to_string(),
                method: method.clone(),
                existing_pattern: Some(path.to_string()),
                reason: format!("Route {} [{}] is registered multiple times", path, method),
            });
        }

        current.routes.insert(method.clone(), route_info);

        // Store named route
        if let Some(n) = name {
            self.named_routes.insert(n, (path.to_string(), method));
        }

        Ok(())
    }

    pub fn get(
        &self,
        path: &str,
        method: &str
    ) -> PyResult<Option<PyObject>> {
        let method = method.to_uppercase();

        // Decode path at Rust level for performance
        let decoded_path = percent_decode_str(path).decode_utf8_lossy();
        let segments: Vec<&str> = decoded_path.split('/').filter(|s| !s.is_empty()).collect();

        // Try exact match
        if let Some((handler, _)) = self.match_route(&segments, &method) {
            return Ok(Some(Python::with_gil(|py| handler.clone_ref(py))));
        }

        // Try with slash policy
        match self.slash_policy {
            SlashPolicy::RedirectToSlash => {
                if !path.ends_with('/') {
                    let alt_path = format!("{}/", path);
                    let alt_segments: Vec<&str> = alt_path.split('/').filter(|s| !s.is_empty()).collect();
                    if let Some((handler, _)) = self.match_route(&alt_segments, &method) {
                        return Ok(Some(Python::with_gil(|py| handler.clone_ref(py))));
                    }
                }
            }
            SlashPolicy::RedirectToNoSlash => {
                if path.ends_with('/') && path.len() > 1 {
                    let alt_path = path.trim_end_matches('/');
                    let alt_segments: Vec<&str> = alt_path.split('/').filter(|s| !s.is_empty()).collect();
                    if let Some((handler, _)) = self.match_route(&alt_segments, &method) {
                        return Ok(Some(Python::with_gil(|py| handler.clone_ref(py))));
                    }
                }
            }
            SlashPolicy::Strict => {}
        }

        Ok(None)
    }

    pub fn get_with_params(
        &self,
        path: &str,
        method: &str
    ) -> PyResult<Option<(PyObject, HashMap<String, String>)>> {
        let method = method.to_uppercase();

        // Decode path at Rust level for performance (like Granian does)
        let decoded_path = percent_decode_str(path).decode_utf8_lossy();
        let segments: Vec<&str> = decoded_path.split('/').filter(|s| !s.is_empty()).collect();

        if let Some((handler, params)) = self.match_route(&segments, &method) {
            return Ok(Some((
                Python::with_gil(|py| handler.clone_ref(py)),
                params
            )));
        }

        Ok(None)
    }

    pub fn allowed_methods(&self, path: &str) -> Vec<String> {
        // Decode path at Rust level
        let decoded_path = percent_decode_str(path).decode_utf8_lossy();
        let segments: Vec<&str> = decoded_path.split('/').filter(|s| !s.is_empty()).collect();
        let mut allowed: Vec<String> = Vec::new();

        // Try to find any route matching this path regardless of method
        if let Some(node) = self.find_node(&segments) {
            for method in node.routes.keys() {
                allowed.push(method.clone());
            }
        }

        allowed.sort();
        allowed
    }

    #[pyo3(signature = (name, params=None))]
    pub fn url_for(
        &self,
        name: &str,
        params: Option<&Bound<'_, PyDict>>
    ) -> PyResult<Option<String>> {
        if let Some((pattern, _method)) = self.named_routes.get(name) {
            let mut url = pattern.clone();

            if let Some(p) = params {
                // Replace parameters in pattern
                for (key, value) in p {
                    let key_str = key.to_string();
                    let value_str = value.to_string();

                    // Try both <key> and <type:key> formats
                    url = url.replace(&format!("<{}>", key_str), &value_str);
                    url = url.replace(&format!("<int:{}>", key_str), &value_str);
                    url = url.replace(&format!("<uuid:{}>", key_str), &value_str);
                    url = url.replace(&format!("<date:{}>", key_str), &value_str);
                    url = url.replace(&format!("<path:{}>", key_str), &value_str);
                }
            }

            Ok(Some(url))
        } else {
            Ok(None)
        }
    }

    pub fn stats(&self) -> RouterStats {
        let mut s = RouterStats::new();
        self.root.accumulate_stats(0, &mut s);
        s
    }

    pub fn conflicts(&self) -> Vec<RouteConflict> {
        self.conflicts.clone()
    }
}

// Private implementation methods
impl Router {
    fn parse_pattern(&self, pattern: &str) -> PyResult<Vec<PatternSegment>> {
        let mut segments = Vec::new();
        let parts: Vec<&str> = pattern.split('/').filter(|s| !s.is_empty()).collect();

        for (idx, part) in parts.iter().enumerate() {
            if part.starts_with('<') && part.ends_with('>') {
                // Dynamic segment
                let inner = &part[1..part.len()-1];
                let (converter, name) = if inner.contains(':') {
                    let parts: Vec<&str> = inner.splitn(2, ':').collect();
                    let conv = Converter::from_name(parts[0]);

                    // Validate that 'path' converter is only in last position
                    if matches!(conv, Converter::Path) && idx != parts.len() - 1 {
                        return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                            format!("<path:{}> must be the last segment in route pattern", parts[1])
                        ));
                    }

                    (conv, parts[1].to_string())
                } else {
                    (Converter::String, inner.to_string())
                };

                segments.push(PatternSegment {
                    is_dynamic: true,
                    name: Some(name),
                    converter,
                    literal: String::new(),
                });
            } else {
                // Static segment
                segments.push(PatternSegment {
                    is_dynamic: false,
                    name: None,
                    converter: Converter::String,
                    literal: part.to_string(),
                });
            }
        }

        Ok(segments)
    }

    fn match_route<'a>(
        &'a self,
        segments: &[&str],
        method: &str,
    ) -> Option<(&'a PyObject, HashMap<String, String>)> {
        // Try to find a matching route with valid conversions
        if let Some(node) = self.find_node_with_validation(segments, method) {
            if let Some(route) = node.routes.get(method) {
                let mut params = HashMap::new();

                // Extract and validate parameters
                let mut seg_idx = 0;
                for spec in &route.segments {
                    if spec.is_dynamic {
                        if seg_idx < segments.len() {
                            let value = segments[seg_idx];
                            // Validate the converter
                            if !spec.converter.validate(value) {
                                return None; // Validation failed
                            }
                            if let Some(ref name) = spec.name {
                                params.insert(name.clone(), value.to_string());
                            }
                        }
                        seg_idx += 1;
                    } else {
                        seg_idx += 1;
                    }
                }

                return Some((&route.handler, params));
            }
        }
        None
    }

    fn find_node_with_validation<'a>(
        &'a self,
        segments: &[&str],
        method: &str,
    ) -> Option<&'a Node> {
        // First find the node structurally
        let mut current = &self.root;

        for segment in segments {
            // Try static match first
            if let Some(child) = current.children.get(*segment) {
                current = child;
            } else if let Some(ref child) = current.dynamic_child {
                // For now, just accept any dynamic - validation happens in match_route
                current = child.as_ref();
            } else {
                return None;
            }
        }

        // Check if this node has the requested method
        if current.routes.contains_key(method) {
            Some(current)
        } else {
            None
        }
    }

    fn find_node<'a>(&'a self, segments: &[&str]) -> Option<&'a Node> {
        let mut current = &self.root;

        for segment in segments {
            // Try static match first
            if let Some(child) = current.children.get(*segment) {
                current = child;
            } else if let Some(ref child) = current.dynamic_child {
                // Accept any dynamic segment for method checking
                current = child.as_ref();
            } else {
                return None;
            }
        }

        Some(current)
    }

    fn detect_conflicts(
        &mut self,
        pattern: &str,
        method: &str,
        segments: &[PatternSegment],
    ) {
        // Check if a similar pattern already exists
        // This is a simplified conflict detection - could be enhanced

        // Look for patterns that might shadow each other
        let has_dynamic = segments.iter().any(|s| s.is_dynamic);

        if has_dynamic {
            // Could conflict with static routes
            let static_pattern: Vec<_> = segments.iter()
                .map(|s| if s.is_dynamic { "*" } else { s.literal.as_str() })
                .collect();

            // This is a basic check - a full implementation would traverse the trie
            // to find actual conflicts
            let pattern_sig = static_pattern.join("/");

            // Log potential shadow warning (simplified)
            if pattern_sig.contains('*') {
                // This could shadow or be shadowed by other routes
                // In a full implementation, we'd check the actual trie structure
            }
        }
    }
}

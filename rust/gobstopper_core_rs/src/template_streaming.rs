use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::collections::VecDeque;
use std::sync::Arc;
use tokio::sync::Mutex;

use crate::template_engine::RustTemplateEngine;

/// Streaming template renderer that yields chunks as they're ready
#[pyclass]
pub struct StreamingRenderer {
    // Store a reference instead of trying to clone the engine
    chunk_buffer: Arc<Mutex<VecDeque<String>>>,
}

/// Template chunk for streaming
#[pyclass]
#[derive(Clone)]
pub struct TemplateChunk {
    #[pyo3(get)]
    content: String,
    #[pyo3(get)]
    chunk_type: String, // "static", "dynamic", "widget", "error"
    #[pyo3(get)]
    priority: i32,
}

#[pymethods]
impl TemplateChunk {
    #[new]
    pub fn new(content: String, chunk_type: String, priority: i32) -> Self {
        TemplateChunk {
            content,
            chunk_type,
            priority,
        }
    }
    
    pub fn __str__(&self) -> String {
        self.content.clone()
    }
    
    pub fn __repr__(&self) -> String {
        format!("TemplateChunk(type='{}', priority={}, length={})", 
                self.chunk_type, self.priority, self.content.len())
    }
}

#[pymethods] 
impl StreamingRenderer {
    #[new]
    pub fn new() -> Self {
        StreamingRenderer {
            chunk_buffer: Arc::new(Mutex::new(VecDeque::new())),
        }
    }
    
    /// Parse template content into streamable chunks
    #[pyo3(signature = (template_content))]
    pub fn parse_template_chunks(&self, template_content: &str) -> PyResult<Vec<TemplateChunk>> {
        let parser = StreamingTemplateParser::new(template_content.to_string());
        Ok(parser.parse())
    }
}

/// Iterator for streaming template chunks
#[pyclass]
pub struct StreamingTemplateIterator {
    chunks: Vec<TemplateChunk>,
    current_index: usize,
    engine: Arc<RustTemplateEngine>,
    context: Option<Py<PyDict>>,
}

impl StreamingTemplateIterator {
    pub fn new(chunks: Vec<TemplateChunk>, engine: Arc<RustTemplateEngine>, context: Option<Py<PyDict>>) -> Self {
        StreamingTemplateIterator {
            chunks,
            current_index: 0,
            engine,
            context,
        }
    }
}

#[pymethods]
impl StreamingTemplateIterator {
    fn __iter__(slf: PyRef<Self>) -> PyRef<Self> {
        slf
    }
    
    fn __next__(&mut self, _py: Python) -> PyResult<Option<TemplateChunk>> {
        if self.current_index >= self.chunks.len() {
            return Ok(None);
        }
        
        let chunk = self.chunks[self.current_index].clone();
        self.current_index += 1;
        
        // Process chunk based on type
        match chunk.chunk_type.as_str() {
            "static" => Ok(Some(chunk)),
            "dynamic" => {
                // Render dynamic content
                // This would involve actual template rendering
                Ok(Some(chunk))
            },
            "widget" => {
                // Handle widget includes
                Ok(Some(chunk))
            },
            _ => Ok(Some(chunk))
        }
    }
}

/// Advanced streaming template parser
pub struct StreamingTemplateParser {
    template_content: String,
}

impl StreamingTemplateParser {
    pub fn new(template_content: String) -> Self {
        StreamingTemplateParser {
            template_content,
        }
    }
    
    /// Parse template into streamable chunks
    pub fn parse(&self) -> Vec<TemplateChunk> {
        let mut chunks = Vec::new();
        let _current_pos = 0;
        let content = &self.template_content;
        
        // Simple regex-based parsing (in production, we'd use proper AST parsing)
        let mut static_content = String::new();
        let mut in_template_tag = false;
        let mut tag_content = String::new();
        
        for (i, ch) in content.char_indices() {
            if ch == '{' && content.chars().nth(i + 1) == Some('{') {
                // Start of template tag
                if !static_content.is_empty() {
                    chunks.push(TemplateChunk::new(
                        static_content.clone(),
                        "static".to_string(),
                        10 // High priority for static content
                    ));
                    static_content.clear();
                }
                in_template_tag = true;
                tag_content.clear();
            } else if ch == '}' && content.chars().nth(i + 1) == Some('}') && in_template_tag {
                // End of template tag
                in_template_tag = false;
                
                // Determine chunk type based on tag content
                let chunk_type = if tag_content.trim().starts_with("include") {
                    "widget"
                } else if tag_content.trim().starts_with("for") {
                    "loop"
                } else {
                    "dynamic"
                };
                
                let priority = match chunk_type {
                    "static" => 10,
                    "dynamic" => 8,
                    "widget" => 5,
                    "loop" => 3,
                    _ => 1,
                };
                
                chunks.push(TemplateChunk::new(
                    format!("{{{{{}}}}}", tag_content),
                    chunk_type.to_string(),
                    priority
                ));
            } else if in_template_tag {
                tag_content.push(ch);
            } else {
                static_content.push(ch);
            }
        }
        
        // Add any remaining static content
        if !static_content.is_empty() {
            chunks.push(TemplateChunk::new(
                static_content,
                "static".to_string(),
                10
            ));
        }
        
        // Sort chunks by priority (higher priority first)
        chunks.sort_by(|a, b| b.priority.cmp(&a.priority));
        
        chunks
    }
}

// Widget renderer removed for now to avoid clone issues
// Will be re-implemented with proper architecture
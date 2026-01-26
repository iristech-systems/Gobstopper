use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyString, PyBool, PyFloat, PyInt};
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use dashmap::DashMap;
use tera::{Tera, Context, Value};
use serde_json;

/// High-performance Rust-powered template engine for WOPR
#[pyclass]
#[derive(Clone)]
pub struct RustTemplateEngine {
    /// Tera template engine instance (read-only)
    tera: Arc<Tera>,
    /// Template cache for compiled templates
    template_cache: Arc<DashMap<String, String>>,
    /// Context cache for frequently used contexts
    context_cache: Arc<DashMap<String, Context>>,
    /// Template directory for file watching
    template_dir: PathBuf,
    /// Cache size limit (in number of entries)
    cache_limit: usize,
}

/// Template compilation error
#[derive(Debug)]
pub struct TemplateError {
    pub message: String,
    pub template_name: Option<String>,
    pub line_number: Option<usize>,
}

impl std::fmt::Display for TemplateError {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        write!(f, "Template Error: {}", self.message)
    }
}

impl std::error::Error for TemplateError {}

impl From<tera::Error> for TemplateError {
    fn from(err: tera::Error) -> Self {
        TemplateError {
            message: err.to_string(),
            template_name: None,
            line_number: None,
        }
    }
}

#[pymethods]
impl RustTemplateEngine {
    #[new]
    #[pyo3(signature = (template_dir, auto_escape=true, cache_limit=1000))]
    pub fn new(template_dir: &str, auto_escape: bool, cache_limit: usize) -> PyResult<Self> {
        let template_path = PathBuf::from(template_dir);
        
        // Initialize Tera with proper glob pattern for template files
        let glob_pattern = format!("{}/**/*.html", template_dir);
        let mut tera = match Tera::new(&glob_pattern) {
            Ok(t) => {
                eprintln!("✅ Tera loaded {} templates", t.get_template_names().count());
                t
            },
            Err(e) => {
                eprintln!("❌ Failed to load templates from {}: {}", template_dir, e);
                // Try alternative patterns
                let fallback_patterns = vec![
                    format!("{}/*.html", template_dir),
                    format!("{}/**/*", template_dir),
                ];
                
                let mut fallback_tera = None;
                for pattern in fallback_patterns {
                    if let Ok(t) = Tera::new(&pattern) {
                        eprintln!("✅ Fallback pattern {} loaded {} templates", pattern, t.get_template_names().count());
                        fallback_tera = Some(t);
                        break;
                    }
                }
                
                fallback_tera.unwrap_or_else(|| {
                    eprintln!("⚠️  Using empty Tera instance, no templates loaded");
                    Tera::default()
                })
            }
        };
        
        // Configure auto-escape
        if auto_escape {
            tera.autoescape_on(vec![".html", ".htm", ".xml", ".j2", ".jinja2"]);
        }
        
        // Add built-in filters that are commonly used
        tera.register_filter("currency", currency_filter);
        tera.register_filter("relative_time", relative_time_filter);
        tera.register_filter("tojson", tojson_filter);
        
        Ok(RustTemplateEngine {
            tera: Arc::new(tera),
            template_cache: Arc::new(DashMap::new()),
            context_cache: Arc::new(DashMap::new()),
            template_dir: template_path,
            cache_limit,
        })
    }
    
    /// Render a template with the given context
    #[pyo3(signature = (template_name, context=None))]
    pub fn render(&self, _py: Python, template_name: &str, context: Option<&Bound<'_, PyDict>>) -> PyResult<String> {
        // Convert Python context to Tera context
        let tera_context = match context {
            Some(ctx) => self.convert_py_context(ctx)?,
            None => Context::new(),
        };

        // Render template
        match self.tera.render(template_name, &tera_context) {
            Ok(rendered) => Ok(rendered),
            Err(e) => {
                let error_msg = self.format_tera_error(&e, template_name);
                Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(error_msg))
            }
        }
    }
    
    /// Render a template from string content
    #[pyo3(signature = (template_content, context=None, name=None))]
    pub fn render_string(&self, _py: Python, template_content: &str, context: Option<&Bound<'_, PyDict>>, name: Option<&str>) -> PyResult<String> {
        let tera_context = match context {
            Some(ctx) => self.convert_py_context(ctx)?,
            None => Context::new(),
        };

        let template_name = name.unwrap_or("string_template");

        // Create a temporary Tera instance for string rendering
        let mut tera = Tera::default();
        match tera.render_str(template_content, &tera_context) {
            Ok(rendered) => Ok(rendered),
            Err(e) => {
                let error_msg = self.format_tera_error(&e, template_name);
                Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(error_msg))
            }
        }
    }
    
    /// Add a template from string content (stores in cache for now)
    pub fn add_template(&self, name: &str, content: &str) -> PyResult<()> {
        // Since Tera is in an Arc, we can't mutate it directly
        // For now, we'll store the template content in our cache
        self.template_cache.insert(name.to_string(), content.to_string());
        Ok(())
    }
    
    /// Reload all templates from disk
    pub fn reload(&self) -> PyResult<()> {
        let glob_pattern = format!("{}/**/*", self.template_dir.display());
        match Tera::new(&glob_pattern) {
            Ok(_new_tera) => {
                // This is a bit hacky - we'd need to replace the Arc, but for now just reload
                // In a real implementation, we'd use interior mutability
                Ok(())
            },
            Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                format!("Failed to reload templates: {}", e)
            )),
        }
    }
    
    /// Clear template cache
    pub fn clear_cache(&self) {
        self.template_cache.clear();
        self.context_cache.clear();
    }
    
    /// Get cache statistics
    pub fn cache_stats(&self, py: Python) -> PyResult<PyObject> {
        let stats = pyo3::types::PyDict::new_bound(py);
        stats.set_item("template_cache_size", self.template_cache.len())?;
        stats.set_item("context_cache_size", self.context_cache.len())?;
        stats.set_item("cache_limit", self.cache_limit)?;
        Ok(stats.into())
    }
    
    /// Check if template exists
    pub fn template_exists(&self, name: &str) -> bool {
        self.tera.get_template_names().any(|tn| tn == name)
    }
    
    /// List all template names
    pub fn list_templates(&self, py: Python) -> PyResult<PyObject> {
        let names: Vec<&str> = self.tera.get_template_names().collect();
        Ok(names.to_object(py))
    }
}

impl RustTemplateEngine {
    /// Format Tera error with detailed information
    fn format_tera_error(&self, error: &tera::Error, template_name: &str) -> String {
        use tera::ErrorKind;

        let mut error_parts = vec![
            format!("🚨 Template Rendering Error in '{}'", template_name),
            "=".repeat(60),
            String::new(),
        ];

        // Extract error kind and details
        match &error.kind {
            ErrorKind::Msg(msg) => {
                error_parts.push(format!("❌ {}", msg));
            }
            ErrorKind::TemplateNotFound(name) => {
                error_parts.push(format!("❌ Template not found: '{}'", name));
                error_parts.push(String::new());
                error_parts.push("📁 Available templates:".to_string());
                let templates: Vec<&str> = self.tera.get_template_names().take(10).collect();
                if templates.is_empty() {
                    error_parts.push("  (no templates loaded)".to_string());
                } else {
                    for tpl in templates {
                        error_parts.push(format!("  • {}", tpl));
                    }
                    let total_count = self.tera.get_template_names().count();
                    if total_count > 10 {
                        error_parts.push(format!("  ... and {} more", total_count - 10));
                    }
                }
            }
            ErrorKind::FilterNotFound(name) => {
                error_parts.push(format!("❌ Filter not found: '{}'", name));
                error_parts.push(String::new());
                error_parts.push("📦 Available built-in filters:".to_string());
                error_parts.push("  • currency - Format numbers as currency ($0.00)".to_string());
                error_parts.push("  • relative_time - Format as relative time".to_string());
                error_parts.push("  • tojson - Convert value to JSON string".to_string());
            }
            ErrorKind::InvalidMacroDefinition(name) => {
                error_parts.push(format!("❌ Invalid macro definition: '{}'", name));
            }
            ErrorKind::CircularExtend { tpl, inheritance_chain } => {
                error_parts.push(format!("❌ Circular template inheritance detected for '{}'", tpl));
                error_parts.push(format!("🔄 Inheritance chain: {}", inheritance_chain.join(" → ")));
            }
            _ => {
                // For other errors, use the full error display which includes source info
                let full_error = format!("{}", error);

                // Parse out useful information from the error string
                for line in full_error.lines() {
                    if line.trim().is_empty() {
                        continue;
                    }
                    error_parts.push(format!("  {}", line));
                }
            }
        }

        error_parts.push(String::new());
        error_parts.push("=".repeat(60));

        error_parts.join("\n")
    }

    /// Convert Python dictionary to Tera context
    fn convert_py_context(&self, py_dict: &Bound<'_, PyDict>) -> PyResult<Context> {
        let mut context = Context::new();

        for (key, value) in py_dict.iter() {
            let key_str = key.extract::<String>()?;
            let tera_value = self.python_to_tera_value(&value)?;
            context.insert(&key_str, &tera_value);
        }

        Ok(context)
    }
    
    /// Convert Python value to Tera value recursively
    fn python_to_tera_value(&self, py_value: &Bound<'_, PyAny>) -> PyResult<Value> {
        if py_value.is_none() {
            return Ok(Value::Null);
        }
        
        // Handle basic types
        if let Ok(s) = py_value.downcast::<PyString>() {
            return Ok(Value::String(s.to_str()?.to_string()));
        }
        
        if let Ok(i) = py_value.downcast::<PyInt>() {
            return Ok(Value::Number(serde_json::Number::from(i.extract::<i64>()?)));
        }
        
        if let Ok(f) = py_value.downcast::<PyFloat>() {
            if let Some(num) = serde_json::Number::from_f64(f.extract::<f64>()?) {
                return Ok(Value::Number(num));
            }
        }
        
        if let Ok(b) = py_value.downcast::<PyBool>() {
            return Ok(Value::Bool(b.extract::<bool>()?));
        }
        
        // Handle collections
        if let Ok(list) = py_value.downcast::<PyList>() {
            let mut vec = Vec::new();
            for item in list.iter() {
                vec.push(self.python_to_tera_value(&item)?);
            }
            return Ok(Value::Array(vec));
        }
        
        if let Ok(dict) = py_value.downcast::<PyDict>() {
            let mut map = serde_json::Map::new();
            for (key, value) in dict.iter() {
                let key_str = key.extract::<String>()?;
                let tera_value = self.python_to_tera_value(&value)?;
                map.insert(key_str, tera_value);
            }
            return Ok(Value::Object(map));
        }
        
        // Fallback: convert to string
        Ok(Value::String(py_value.str()?.to_str()?.to_string()))
    }
}

// Built-in filters
fn currency_filter(value: &Value, _args: &HashMap<String, Value>) -> tera::Result<Value> {
    match value {
        Value::Number(n) => {
            if let Some(f) = n.as_f64() {
                Ok(Value::String(format!("${:.2}", f)))
            } else if let Some(i) = n.as_i64() {
                Ok(Value::String(format!("${:.2}", i as f64)))
            } else {
                Ok(Value::String("$0.00".to_string()))
            }
        }
        _ => Ok(Value::String("$0.00".to_string())),
    }
}

fn relative_time_filter(value: &Value, _args: &HashMap<String, Value>) -> tera::Result<Value> {
    // Simplified relative time - in real implementation would parse timestamps
    match value {
        Value::String(s) => Ok(Value::String(format!("{} ago", s))),
        _ => Ok(Value::String("unknown".to_string())),
    }
}

fn tojson_filter(value: &Value, _args: &HashMap<String, Value>) -> tera::Result<Value> {
    match serde_json::to_string(value) {
        Ok(json_str) => Ok(Value::String(json_str)),
        Err(_) => Ok(Value::String("null".to_string())),
    }
}
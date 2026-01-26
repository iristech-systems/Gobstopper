use pyo3::prelude::*;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use notify::{Event, RecommendedWatcher, Watcher};
use tokio::sync::mpsc;
use dashmap::DashMap;

use crate::template_engine::RustTemplateEngine;

/// File watcher for hot template reloading
#[pyclass]
pub struct TemplateWatcher {
    template_dir: PathBuf,
    engine: Arc<RustTemplateEngine>,
    watcher: Option<RecommendedWatcher>,
    dependency_map: Arc<DashMap<String, Vec<String>>>, // template -> dependencies
    reverse_dependency_map: Arc<DashMap<String, Vec<String>>>, // dependency -> templates
    is_watching: bool,
}

/// Template change event
#[pyclass]
#[derive(Clone, Debug)]
pub struct TemplateChangeEvent {
    #[pyo3(get)]
    pub path: String,
    #[pyo3(get)]
    pub event_type: String, // "created", "modified", "deleted", "renamed"
    #[pyo3(get)]
    pub template_name: String,
    #[pyo3(get)]
    pub affected_templates: Vec<String>, // Templates that depend on this one
}

#[pymethods]
impl TemplateChangeEvent {
    fn __repr__(&self) -> String {
        format!("TemplateChangeEvent(path='{}', type='{}', template='{}')", 
                self.path, self.event_type, self.template_name)
    }
}

#[pymethods]
impl TemplateWatcher {
    #[new]
    #[pyo3(signature = (template_dir, engine, watch_immediately=true))]
    pub fn new(template_dir: &str, engine: &RustTemplateEngine, watch_immediately: bool) -> PyResult<Self> {
        let mut watcher = TemplateWatcher {
            template_dir: PathBuf::from(template_dir),
            engine: Arc::new(engine.clone()), // Will need to fix clone
            watcher: None,
            dependency_map: Arc::new(DashMap::new()),
            reverse_dependency_map: Arc::new(DashMap::new()),
            is_watching: false,
        };
        
        if watch_immediately {
            watcher.start_watching()?;
        }
        
        Ok(watcher)
    }
    
    /// Start watching for template changes
    pub fn start_watching(&mut self) -> PyResult<()> {
        if self.is_watching {
            return Ok(()); // Already watching
        }
        
        let template_dir = self.template_dir.clone();
        let engine = self.engine.clone();
        let dependency_map = self.dependency_map.clone();
        let reverse_dependency_map = self.reverse_dependency_map.clone();
        
        // Create file system watcher
        let (tx, mut rx) = mpsc::channel(100);
        
        let mut watcher = notify::recommended_watcher(move |res: Result<Event, notify::Error>| {
            match res {
                Ok(event) => {
                    if let Err(e) = tx.blocking_send(event) {
                        eprintln!("Failed to send file event: {}", e);
                    }
                }
                Err(e) => eprintln!("File watch error: {:?}", e),
            }
        }).map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
            format!("Failed to create file watcher: {}", e)
        ))?;
        
        watcher.watch(&template_dir, notify::RecursiveMode::Recursive)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                format!("Failed to watch directory: {}", e)
            ))?;
        
        self.watcher = Some(watcher);
        self.is_watching = true;
        
        // Spawn background task to handle file events
        tokio::spawn(async move {
            while let Some(event) = rx.recv().await {
                Self::handle_file_event(
                    event, 
                    &template_dir, 
                    &engine, 
                    &dependency_map, 
                    &reverse_dependency_map
                ).await;
            }
        });
        
        Ok(())
    }
    
    /// Stop watching for template changes
    pub fn stop_watching(&mut self) -> PyResult<()> {
        if let Some(watcher) = self.watcher.take() {
            drop(watcher); // Dropping the watcher stops it
        }
        self.is_watching = false;
        Ok(())
    }
    
    /// Build dependency map by analyzing template includes
    pub fn build_dependency_map(&self, py: Python) -> PyResult<()> {
        // Scan all templates to find includes and extends
        let templates = self.engine.list_templates(py)?;
        
        for template_name in templates.extract::<Vec<String>>(py)? {
            let dependencies = self.analyze_template_dependencies(&template_name)?;
            
            // Store forward dependencies
            self.dependency_map.insert(template_name.clone(), dependencies.clone());
            
            // Store reverse dependencies
            for dep in dependencies {
                self.reverse_dependency_map
                    .entry(dep)
                    .or_insert_with(Vec::new)
                    .push(template_name.clone());
            }
        }
        
        Ok(())
    }
    
    /// Get templates that depend on a given template
    pub fn get_dependent_templates(&self, template_name: &str) -> Vec<String> {
        self.reverse_dependency_map
            .get(template_name)
            .map(|deps| deps.clone())
            .unwrap_or_default()
    }
    
    /// Get dependencies of a given template
    pub fn get_template_dependencies(&self, template_name: &str) -> Vec<String> {
        self.dependency_map
            .get(template_name)
            .map(|deps| deps.clone())
            .unwrap_or_default()
    }
    
    /// Clear all dependency mappings
    pub fn clear_dependency_cache(&self) {
        self.dependency_map.clear();
        self.reverse_dependency_map.clear();
    }
    
    /// Check if currently watching
    pub fn is_watching(&self) -> bool {
        self.is_watching
    }
}

impl TemplateWatcher {
    /// Handle file system events
    async fn handle_file_event(
        event: Event,
        template_dir: &Path,
        engine: &RustTemplateEngine,
        dependency_map: &DashMap<String, Vec<String>>,
        reverse_dependency_map: &DashMap<String, Vec<String>>
    ) {
        use notify::EventKind;
        
        for path in event.paths {
            if !Self::is_template_file(&path) {
                continue;
            }
            
            let template_name = match Self::path_to_template_name(&path, template_dir) {
                Some(name) => name,
                None => continue,
            };
            
            let event_type = match event.kind {
                EventKind::Create(_) => "created",
                EventKind::Modify(_) => "modified", 
                EventKind::Remove(_) => "deleted",
                EventKind::Other => "other",
                _ => "unknown",
            };
            
            println!("Template {} {}: {}", event_type, template_name, path.display());
            
            match event_type {
                "created" | "modified" => {
                    // Reload the changed template
                    if let Err(e) = Self::reload_template(engine, &template_name).await {
                        eprintln!("Failed to reload template {}: {}", template_name, e);
                    }
                    
                    // Reload dependent templates
                    if let Some(dependents) = reverse_dependency_map.get(&template_name) {
                        for dependent in dependents.iter() {
                            if let Err(e) = Self::reload_template(engine, dependent).await {
                                eprintln!("Failed to reload dependent template {}: {}", dependent, e);
                            }
                        }
                    }
                },
                "deleted" => {
                    // Clear from dependency maps
                    dependency_map.remove(&template_name);
                    reverse_dependency_map.remove(&template_name);
                    
                    // Clear template cache
                    engine.clear_cache();
                },
                _ => {}
            }
        }
    }
    
    /// Reload a specific template
    async fn reload_template(engine: &RustTemplateEngine, template_name: &str) -> Result<(), Box<dyn std::error::Error>> {
        // For now, just clear the cache - in a full implementation we'd reload from disk
        engine.clear_cache();
        
        println!("Reloaded template: {}", template_name);
        Ok(())
    }
    
    /// Check if a file is a template file
    fn is_template_file(path: &Path) -> bool {
        if let Some(extension) = path.extension() {
            matches!(extension.to_str(), Some("html") | Some("htm") | Some("j2") | Some("jinja2") | Some("xml"))
        } else {
            false
        }
    }
    
    /// Convert file path to template name
    fn path_to_template_name(path: &Path, template_dir: &Path) -> Option<String> {
        path.strip_prefix(template_dir)
            .ok()?
            .to_str()
            .map(|s| s.replace('\\', "/"))
    }
    
    /// Analyze template to find its dependencies
    fn analyze_template_dependencies(&self, _template_name: &str) -> PyResult<Vec<String>> {
        // This is a simplified implementation
        // In reality, we'd parse the template AST to find all includes, extends, and imports
        
        let dependencies = Vec::new();
        
        // For now, return empty dependencies
        // TODO: Implement proper template parsing to extract:
        // - {% extends "base.html" %}
        // - {% include "widget.html" %}  
        // - {% import "macros.html" as m %}
        
        Ok(dependencies)
    }
}

/// Template dependency analyzer
pub struct DependencyAnalyzer {
    template_content: String,
}

impl DependencyAnalyzer {
    pub fn new(template_content: String) -> Self {
        DependencyAnalyzer {
            template_content,
        }
    }
    
    /// Extract all template dependencies
    pub fn extract_dependencies(&self) -> Vec<String> {
        let mut dependencies = Vec::new();
        let _content = &self.template_content;
        
        // Simple regex-based extraction (in production, use proper parsing)
        
        // Find extends statements
        if let Some(extends) = self.extract_extends() {
            dependencies.push(extends);
        }
        
        // Find include statements
        dependencies.extend(self.extract_includes());
        
        // Find import statements  
        dependencies.extend(self.extract_imports());
        
        dependencies
    }
    
    fn extract_extends(&self) -> Option<String> {
        // Look for {% extends "template.html" %}
        use regex::Regex;
        let re = Regex::new(r#"\{\%\s*extends\s+["']([^"']+)["']\s*\%\}"#).unwrap();
        
        if let Some(cap) = re.captures(&self.template_content) {
            return cap.get(1).map(|m| m.as_str().to_string());
        }
        
        None
    }
    
    fn extract_includes(&self) -> Vec<String> {
        // Look for {% include "template.html" %}
        use regex::Regex;
        let re = Regex::new(r#"\{\%\s*include\s+["']([^"']+)["']\s*\%\}"#).unwrap();
        
        re.captures_iter(&self.template_content)
            .filter_map(|cap| cap.get(1).map(|m| m.as_str().to_string()))
            .collect()
    }
    
    fn extract_imports(&self) -> Vec<String> {
        // Look for {% import "template.html" as name %}
        use regex::Regex;
        let re = Regex::new(r#"\{\%\s*import\s+["']([^"']+)["']\s+as\s+\w+\s*\%\}"#).unwrap();
        
        re.captures_iter(&self.template_content)
            .filter_map(|cap| cap.get(1).map(|m| m.as_str().to_string()))
            .collect()
    }
}
use pyo3::prelude::*;

mod routing;
mod json;
mod static_files;
mod template_engine;
mod template_streaming;
mod template_watcher;

/// A Python module implemented in Rust.
#[pymodule]
fn _core(py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    // HTTP routing
    m.add_class::<routing::Router>()?;
    m.add_class::<routing::RouterStats>()?;
    m.add_class::<routing::RouteConflict>()?;
    m.add_class::<routing::SlashPolicy>()?;

    // Static file serving
    m.add_class::<static_files::StaticHandler>()?;

    // Template engine
    m.add_class::<template_engine::RustTemplateEngine>()?;

    // Streaming templates
    m.add_class::<template_streaming::StreamingRenderer>()?;
    m.add_class::<template_streaming::TemplateChunk>()?;
    m.add_class::<template_streaming::StreamingTemplateIterator>()?;

    // Hot reloading
    m.add_class::<template_watcher::TemplateWatcher>()?;
    m.add_class::<template_watcher::TemplateChangeEvent>()?;

    // JSON utilities
    json::register_json_functions(py, m)?;

    Ok(())
}

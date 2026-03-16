use pyo3::prelude::*;

mod routing;
mod json;
mod static_files;

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

    // JSON utilities
    json::register_json_functions(py, m)?;

    Ok(())
}

use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use pythonize::pythonize;
use serde_json::Value;

/// Parse JSON from byte slice and return Python object
#[pyfunction]
pub fn from_slice(py: Python, data: &[u8]) -> PyResult<PyObject> {
    let json_value: Value = serde_json::from_slice(data)
        .map_err(|e| PyValueError::new_err(format!("JSON parse error: {}", e)))?;

    let bound_obj = pythonize(py, &json_value)
        .map_err(|e| PyValueError::new_err(format!("Conversion error: {}", e)))?;

    Ok(bound_obj.unbind())
}

/// Parse JSON from string and return Python object
#[pyfunction]
pub fn from_str(py: Python, data: &str) -> PyResult<PyObject> {
    let json_value: Value = serde_json::from_str(data)
        .map_err(|e| PyValueError::new_err(format!("JSON parse error: {}", e)))?;

    let bound_obj = pythonize(py, &json_value)
        .map_err(|e| PyValueError::new_err(format!("Conversion error: {}", e)))?;

    Ok(bound_obj.unbind())
}

/// Register the JSON functions with the module
pub fn register_json_functions(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(from_slice, m)?)?;
    m.add_function(wrap_pyfunction!(from_str, m)?)?;
    Ok(())
}

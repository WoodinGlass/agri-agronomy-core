#![forbid(unsafe_code)]
#![deny(
    clippy::unwrap_used,
    clippy::expect_used,
    clippy::panic,
    clippy::indexing_slicing
)]
// PackError mirrors Python's exception classes, including the `findings`
// field for batch reports. `Result<T, PackError>` is over clippy's
// 128-byte threshold by design; boxing would force `.map_err(|e| *e)` at
// every call site across tables/build/validate. Revisit in M21.5 (pure).
#![allow(clippy::result_large_err)]

//! Native kernel for agri-agronomy-core. Lives behind `agri_core._native`.

pub mod canonical;
pub mod hash;
pub mod pack;
pub mod request_id;

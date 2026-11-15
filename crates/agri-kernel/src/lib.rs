#![forbid(unsafe_code)]
#![deny(
    clippy::unwrap_used,
    clippy::expect_used,
    clippy::panic,
    clippy::indexing_slicing
)]

//! Native kernel for agri-agronomy-core. Lives behind `agri_core._native`.

pub mod canonical;
pub mod hash;
pub mod pack;
pub mod request_id;

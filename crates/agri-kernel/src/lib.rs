#![forbid(unsafe_code)]
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

//! Native kernel for agri-agronomy-core. Lives behind `agri_core._native`.

pub mod canonical;
pub mod hash;
pub mod request_id;

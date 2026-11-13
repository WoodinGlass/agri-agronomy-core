//! SHA-256 helpers. Only `sha256_hex` in M20a. `pack_hash_files` is M21.

use sha2::{Digest, Sha256};

pub fn sha256_hex(data: &[u8]) -> String {
    let mut h = Sha256::new();
    h.update(data);
    let digest = h.finalize();
    // sha2 0.11 returns an Array that does not implement LowerHex;
    // format manually to match Python hashlib.sha256(...).hexdigest().
    let mut out = String::with_capacity(digest.len() * 2);
    for byte in digest.iter() {
        use std::fmt::Write as _;
        let _ = write!(out, "{:02x}", byte);
    }
    out
}

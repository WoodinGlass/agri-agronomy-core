use agri_kernel::pack::verify::hash_pack_files;
use base64::Engine;
use std::collections::HashMap;

#[test]
fn reads_shared_hash_pack_files_vectors() {
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/vectors/hash_pack_files.json"
    );
    let data = std::fs::read_to_string(path).expect("hash_pack_files.json readable");
    let corpus: serde_json::Value = serde_json::from_str(&data).expect("valid json");
    let cases = corpus.as_array().expect("array of cases");
    let engine = base64::engine::general_purpose::STANDARD;
    let mut n = 0;
    for case in cases {
        let name = case["name"].as_str().expect("name");
        let hash_alg = case["hash_alg"].as_str().expect("hash_alg");
        let expected = case["expected"].as_str().expect("expected");
        let files_json = case["files_b64"].as_object().expect("files_b64 object");
        let mut files: HashMap<String, Vec<u8>> = HashMap::new();
        for (k, v) in files_json {
            let b64 = v.as_str().expect("b64 string");
            let bytes = engine.decode(b64).expect("valid base64");
            files.insert(k.clone(), bytes);
        }
        let actual =
            hash_pack_files(&files, hash_alg).unwrap_or_else(|e| panic!("case {name}: {e}"));
        assert_eq!(actual, expected, "case {name}");
        n += 1;
    }
    assert!(n >= 10, "expected >=10 cases, got {n}");
}

use agri_kernel::canonical::canonical_json;

#[test]
fn reads_shared_vectors() {
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/vectors/canonical.json"
    );
    let data = std::fs::read_to_string(path).expect("canonical.json readable");
    let corpus: serde_json::Value = serde_json::from_str(&data).expect("valid json");
    let cases = corpus.as_array().expect("array of cases");
    let mut n = 0;
    for case in cases {
        let input = &case["input"];
        let expected = case["expected"].as_str().expect("expected string");
        let out = canonical_json(input).expect("canonical");
        let actual = std::str::from_utf8(&out).unwrap();
        assert_eq!(actual, expected, "case: {input:?}");
        n += 1;
    }
    assert!(n >= 20, "expected at least 20 cases, got {n}");
}

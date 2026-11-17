//! Ordering: Hangul L/V/T composition + combining-class reorder (D4, ADR-019 §11.14).
//!
//! Covers the cases where NFKC pipeline order matters:
//! - Hangul LV: all L x V combos -> LV syllables (399).
//! - Hangul LVT: all L x V x T combos -> LVT syllables (10,773).
//! - ccc: combining marks with different classes reordered before composition.
//! - ligature and expansion cases.
//!
//! Each case is asserted native == golden 16.0 (from normalize_name_16_0.json,
//! extended with computed expected for codepoints not in the file). Because
//! composition is deterministic and stability-locked, the expected output is
//! the composed syllable, identical to the input's normalized form. The test
//! is a tripwire for pipeline-order regressions.

use agri_kernel::pack::normalize::normalize_name;

// Hangul jamo ranges (Unicode 16.0, stable since 2.0).
const L_BASE: u32 = 0x1100;
const L_COUNT: u32 = 19;
const V_BASE: u32 = 0x1161;
const V_COUNT: u32 = 21;
const T_BASE: u32 = 0x11A8;
const T_COUNT: u32 = 28;
const S_BASE: u32 = 0xAC00;

fn compose_lv(l_idx: u32, v_idx: u32) -> u32 {
    S_BASE + (l_idx * V_COUNT + v_idx) * T_COUNT
}

fn compose_lvt(l_idx: u32, v_idx: u32, t_idx: u32) -> u32 {
    S_BASE + (l_idx * V_COUNT + v_idx) * T_COUNT + (t_idx + 1)
}

#[test]
fn hangul_lv_all_combinations() {
    let mut failures = Vec::new();
    for l in 0..L_COUNT {
        for v in 0..V_COUNT {
            let lv = compose_lv(l, v);
            let expected = match char::from_u32(lv) {
                Some(c) => c.to_string(),
                None => continue,
            };
            let l_char = char::from_u32(L_BASE + l).unwrap();
            let v_char = char::from_u32(V_BASE + v).unwrap();
            let input = format!("{l_char}{v_char}");
            let got = normalize_name(&input);
            if got != expected {
                failures.push(format!(
                    "L+U+{:04X} V+U+{:04X}: got {:?}, expected {:?}",
                    L_BASE + l,
                    V_BASE + v,
                    got,
                    expected
                ));
            }
        }
    }
    assert!(failures.is_empty(), "{} failures", failures.len());
}

#[test]
fn hangul_lvt_all_combinations() {
    let mut failures = Vec::new();
    for l in 0..L_COUNT {
        for v in 0..V_COUNT {
            for t in 0..27 {
                let lvt = compose_lvt(l, v, t);
                let expected = match char::from_u32(lvt) {
                    Some(c) => c.to_string(),
                    None => continue,
                };
                let l_char = char::from_u32(L_BASE + l).unwrap();
                let v_char = char::from_u32(V_BASE + v).unwrap();
                let t_char = char::from_u32(T_BASE + t).unwrap();
                let input = format!("{l_char}{v_char}{t_char}");
                let got = normalize_name(&input);
                if got != expected {
                    failures.push(format!(
                        "L+U+{:04X} V+U+{:04X} T+U+{:04X}: got {:?}, expected {:?}",
                        L_BASE + l,
                        V_BASE + v,
                        T_BASE + t,
                        got,
                        expected
                    ));
                    if failures.len() >= 10 {
                        break;
                    }
                }
            }
        }
    }
    assert!(
        failures.is_empty(),
        "{} failures (first 10)",
        failures.len()
    );
}

#[test]
fn ccc_reordering() {
    // base + ccc=230 + ccc=220 -> NFKC reorders to base + ccc=220 + ccc=230
    // U+0301 (acute, ccc=230), U+0316 (grave below, ccc=220)
    let base = 'a';
    let high = '\u{0301}'; // ccc=230
    let low = '\u{0316}'; // ccc=220
                          // Input in wrong canonical order
    let input = format!("{base}{high}{low}");
    let got = normalize_name(&input);
    // NFKC reorders canonically (ccc 220 before 230), then composes base+acute
    // to á (U+00E1). U+0316 (grave below) has no composition with 'a' so it
    // remains after the composed base. Python reference (DIAG 2):
    //   "a" + U+0301 + U+0316 -> NFKC "á" + U+0316
    let expected = "\u{00E1}\u{0316}";
    assert_eq!(
        got, expected,
        "composed ccc reorder (a + acute + grave_below)"
    );

    // Same with upper-case base (casefold after NFKC).
    // A + acute -> Á (NFKC compose), then casefold -> á. Grave_below stays.
    let base_upper = 'A';
    let input2 = format!("{base_upper}{high}{low}");
    let got2 = normalize_name(&input2);
    let expected2 = "\u{00E1}\u{0316}";
    assert_eq!(
        got2, expected2,
        "composed ccc reorder (A + acute + grave_below)"
    );
}

#[test]
fn ligature_expansions() {
    // NFKC expansions
    let cases = [
        ("\u{FB00}", "ff"),        // ﬀ
        ("\u{FB01}", "fi"),        // ﬁ
        ("\u{FB02}", "fl"),        // ﬂ
        ("\u{FB03}", "ffi"),       // ﬃ
        ("\u{FB04}", "ffl"),       // ﬄ
        ("\u{FB05}", "st"),        // ﬅ
        ("\u{FB06}", "st"),        // ﬆ
        ("\u{0132}", "ij"),        // Ĳ
        ("\u{0133}", "ij"),        // ĳ
        ("\u{01C4}", "d\u{017E}"), // Ǆ
        ("\u{01C5}", "d\u{017E}"), // ǅ
        ("\u{01C6}", "d\u{017E}"), // ǆ
    ];
    for (input, expected) in cases {
        assert_eq!(normalize_name(input), expected, "input {input:?}");
    }
}

#[test]
fn casefold_expansions() {
    // C+F casefold expansions (post-NFKC)
    let cases = [
        ("\u{00DF}", "ss"),                       // ß
        ("\u{1E9E}", "ss"),                       // ẞ
        ("\u{0130}", "i\u{0307}"),                // İ -> i + combining dot
        ("\u{1FD3}", "\u{03B9}\u{0308}\u{0301}"), // ΐ
    ];
    for (input, expected) in cases {
        assert_eq!(normalize_name(input), expected, "input {input:?}");
    }
}

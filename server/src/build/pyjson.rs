//! JSON text in the format of `json.dumps(value, ensure_ascii=False)` in Python: ", " between the
//! items, ": " after a key, and the keys of an object in their order. The JSON columns of the
//! shows table have this format since the first version of the app, and the build keeps it.

use serde::Deserialize;
use serde::de::{Deserializer, MapAccess, Visitor};
use serde_json::Value;

/// A JSON object that keeps the order of its keys, as a dict of Python does
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Ordered(pub Vec<(String, Value)>);

impl<'de> Deserialize<'de> for Ordered {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct Keys;
        impl<'de> Visitor<'de> for Keys {
            type Value = Ordered;
            fn expecting(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
                f.write_str("an object")
            }
            fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Ordered, A::Error> {
                let mut out: Vec<(String, Value)> = Vec::new();
                while let Some((key, value)) = map.next_entry::<String, Value>()? {
                    // A key that comes again replaces the value at its first place, as in a dict
                    match out.iter_mut().find(|(k, _)| *k == key) {
                        Some(slot) => slot.1 = value,
                        None => out.push((key, value)),
                    }
                }
                Ok(Ordered(out))
            }
            fn visit_unit<E>(self) -> Result<Ordered, E> {
                Ok(Ordered::default())
            }
        }
        deserializer.deserialize_any(Keys)
    }
}

/// `repr(float)` of Python: the shortest text that gives the same number
pub fn float_repr(x: f64) -> String {
    if x.is_nan() {
        return "NaN".into();
    }
    if x.is_infinite() {
        return if x > 0.0 { "Infinity".into() } else { "-Infinity".into() };
    }
    if x == 0.0 {
        return if x.is_sign_negative() { "-0.0".into() } else { "0.0".into() };
    }
    // The shortest digits and the exponent, from the scientific format of Rust
    let sci = format!("{x:e}");
    let (mantissa, exponent) = sci.split_once('e').unwrap();
    let exponent: i32 = exponent.parse().unwrap();
    let negative = mantissa.starts_with('-');
    let digits: String = mantissa.chars().filter(char::is_ascii_digit).collect();
    let sign = if negative { "-" } else { "" };
    if !(-4..16).contains(&exponent) {
        let rest = if digits.len() > 1 { format!(".{}", &digits[1..]) } else { String::new() };
        let mark = if exponent < 0 { '-' } else { '+' };
        return format!("{sign}{}{rest}e{mark}{:02}", &digits[..1], exponent.abs());
    }
    let point = exponent + 1;
    let text = if point <= 0 {
        format!("0.{}{digits}", "0".repeat((-point) as usize))
    } else if point as usize >= digits.len() {
        format!("{digits}{}.0", "0".repeat(point as usize - digits.len()))
    } else {
        format!("{}.{}", &digits[..point as usize], &digits[point as usize..])
    };
    format!("{sign}{text}")
}

fn number(n: &serde_json::Number) -> String {
    if n.is_f64() { float_repr(n.as_f64().unwrap()) } else { n.to_string() }
}

/// The text of a JSON string: the same escapes as Python with ensure_ascii=False
fn string(s: &str) -> String {
    serde_json::to_string(s).unwrap()
}

/// `json.dumps(value, ensure_ascii=False)`
pub fn dumps(value: &Value) -> String {
    match value {
        Value::Null => "null".into(),
        Value::Bool(b) => if *b { "true" } else { "false" }.into(),
        Value::Number(n) => number(n),
        Value::String(s) => string(s),
        Value::Array(items) => format!("[{}]", items.iter().map(dumps).collect::<Vec<_>>().join(", ")),
        Value::Object(map) => format!("{{{}}}", map.iter().map(|(k, v)| format!("{}: {}", string(k), dumps(v))).collect::<Vec<_>>().join(", ")),
    }
}

/// `json.dumps` of an object with its keys in their order
pub fn dumps_ordered(object: &Ordered) -> String {
    format!("{{{}}}", object.0.iter().map(|(k, v)| format!("{}: {}", string(k), dumps(v))).collect::<Vec<_>>().join(", "))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn the_text_is_the_text_of_python() {
        assert_eq!(dumps(&json!(["Action", "Slice of Life"])), r#"["Action", "Slice of Life"]"#);
        assert_eq!(dumps(&json!([[101, 6], [102, 16]])), "[[101, 6], [102, 16]]");
        assert_eq!(dumps(&json!([])), "[]");
        assert_eq!(dumps(&json!(["日本", "a\"b\\c\nd\u{1}"])), "[\"日本\", \"a\\\"b\\\\c\\nd\\u0001\"]");
        let object: Ordered = serde_json::from_str(r#"{"tvdb": "1", "imdb": "tt2", "tmdb": "3"}"#).unwrap();
        assert_eq!(dumps_ordered(&object), r#"{"tvdb": "1", "imdb": "tt2", "tmdb": "3"}"#);
    }

    #[test]
    fn floats_have_the_repr_of_python() {
        for (x, text) in [(7.5, "7.5"), (1.0, "1.0"), (0.1, "0.1"), (1e-5, "1e-05"), (0.0001, "0.0001"), (1e16, "1e+16"), (123456789.0, "123456789.0"), (-2.5e-7, "-2.5e-07"), (0.3, "0.3")] {
            assert_eq!(float_repr(x), text, "{x}");
        }
    }
}

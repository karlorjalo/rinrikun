//! The embeddings of the shows: the text of a row, the hash of the text, and the vectors of the
//! EmbeddingGemma model (ONNX) with ONNX Runtime. The texts and the hashes are the texts and the
//! hashes of the first version of the app: a change makes all stored embeddings old.
//!
//! EmbeddingGemma 2 is multilingual: the library rows are in Japanese and the AniList rows in
//! English. The model files come from the cache of Hugging Face, or the build downloads them. The
//! model runs on the GPU with DirectML (see `gpu_session`), else on the CPU.

use std::path::{Path, PathBuf};
use std::time::Duration;

use anyhow::{Context, Result, anyhow, bail};
use ort::session::Session;
use ort::value::{Tensor, ValueType};
use serde_json::{Map, Value};
use tokenizers::Tokenizer;

use super::pyjson::float_repr;

pub const MODEL: &str = "onnx-community/embeddinggemma-2-ONNX";
const MODEL_FILE: &str = "onnx/model.onnx";
/// The model card gives this prefix for texts that are compared with each other
pub const PROMPT: &str = "task: sentence similarity | query: ";
pub const DIM: usize = 768;
const BATCH_SIZE: usize = 32;
const MAX_TOKENS: usize = 2048;

/// The text of a value of a row, as `str(value)` of Python (the texts of the hashes)
fn value_text(value: Option<&Value>) -> String {
    match value {
        None | Some(Value::Null) => "None".into(),
        Some(Value::String(s)) => s.clone(),
        Some(Value::Bool(b)) => if *b { "True" } else { "False" }.into(),
        Some(Value::Number(n)) if n.is_f64() => float_repr(n.as_f64().unwrap()),
        Some(other) => other.to_string(),
    }
}

fn first_texts(value: Option<&Value>, count: usize) -> Vec<String> {
    value.and_then(Value::as_array).map(|a| a.iter().take(count).map(|v| value_text(Some(v))).collect()).unwrap_or_default()
}

/// `build_text`: the text of a row for the model
pub fn build_text(r: &Map<String, Value>) -> String {
    let truthy = |key: &str| r.get(key).is_some_and(crate::store::truthy);
    // `r.get('title_native') or r.get('title', '')`
    let name = if truthy("title_native") {
        value_text(r.get("title_native"))
    } else if r.contains_key("title") {
        value_text(r.get("title"))
    } else {
        String::new()
    };
    let mut out = format!("{name} ({})", value_text(r.get("title")));
    if truthy("year") {
        out.push_str(&format!(". {}", value_text(r.get("year"))));
    }
    if truthy("genres") {
        out.push_str(&format!(". Genres: {}", first_texts(r.get("genres"), 6).join(", ")));
    }
    if truthy("tags") {
        out.push_str(&format!(". Tags: {}", first_texts(r.get("tags"), 24).join(", ")));
    }
    if truthy("studios") {
        out.push_str(&format!(". Studios: {}", first_texts(r.get("studios"), 3).join(", ")));
    }
    if truthy("overview") {
        let overview = value_text(r.get("overview"));
        out.push_str(". ");
        out.extend(overview.chars().take(1200));
    }
    out
}

/// `text_hash`: the model and the prompt are part of the hash. Thus a change of one of them makes
/// all kept embeddings old.
pub fn text_hash(r: &Map<String, Value>) -> String {
    sha1_smol::Sha1::from(format!("{MODEL}\n{PROMPT}\n{}", build_text(r))).digest().to_string()
}

/// The folder of the model in the cache of Hugging Face, if the cache has all files
fn cached_model() -> Option<PathBuf> {
    let hub = std::env::var_os("HF_HUB_CACHE")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HF_HOME").map(|h| PathBuf::from(h).join("hub")))
        .or_else(|| std::env::var_os("USERPROFILE").or_else(|| std::env::var_os("HOME")).map(|h| PathBuf::from(h).join(".cache").join("huggingface").join("hub")))?;
    let folder = hub.join(format!("models--{}", MODEL.replace('/', "--")));
    let revision = std::fs::read_to_string(folder.join("refs").join("main")).ok()?;
    let snapshot = folder.join("snapshots").join(revision.trim());
    let complete = [MODEL_FILE, &format!("{MODEL_FILE}_data"), "tokenizer.json"].iter().all(|f| snapshot.join(f).is_file());
    complete.then_some(snapshot)
}

/// Download the files of the model into `folder`. The first download is about 1.1 GB.
fn download_model(folder: &Path) -> Result<()> {
    let agent: ureq::Agent = ureq::Agent::config_builder().timeout_connect(Some(Duration::from_secs(30))).build().into();
    for file in [MODEL_FILE.to_string(), format!("{MODEL_FILE}_data"), "tokenizer.json".to_string()] {
        let target = folder.join(&file);
        if target.is_file() {
            continue;
        }
        println!("downloading {file} of {MODEL}");
        std::fs::create_dir_all(target.parent().unwrap())?;
        let part = target.with_extension("part");
        let mut answer = agent.get(&format!("https://huggingface.co/{MODEL}/resolve/main/{file}")).call().with_context(|| format!("cannot download {file}"))?;
        let mut out = std::fs::File::create(&part)?;
        std::io::copy(&mut answer.body_mut().as_reader(), &mut out)?;
        drop(out);
        std::fs::rename(&part, &target)?;
    }
    Ok(())
}

/// The tokenizer and the session of the model
pub struct Embedder {
    tokenizer: Tokenizer,
    session: Session,
    /// The inputs for pictures, video and audio: empty arrays for a text
    extra: Vec<(String, Vec<i64>)>,
}

/// A session of the model on the GPU with DirectML (DirectX 12): the NVIDIA card of the PC, or
/// another GPU. ONNX Runtime needs DirectML.dll next to the program. DirectML does not permit
/// the memory pattern and the parallel execution of ONNX Runtime.
fn gpu_session(model: &Path) -> Result<Session> {
    let provider = ort::ep::DirectML::default()
        .with_device_filter(ort::ep::directml::DeviceFilter::Gpu)
        .with_performance_preference(ort::ep::directml::PerformancePreference::HighPerformance)
        .build()
        .error_on_failure();
    Session::builder()
        .map_err(|e| anyhow!("{e}"))?
        .with_memory_pattern(false)
        .map_err(|e| anyhow!("{e}"))?
        .with_parallel_execution(false)
        .map_err(|e| anyhow!("{e}"))?
        .with_execution_providers([provider])
        .map_err(|e| anyhow!("{e}"))?
        .commit_from_file(model)
        .map_err(|e| anyhow!("cannot load the model: {e}"))
}

/// A session of the model on the CPU
fn cpu_session(model: &Path) -> Result<Session> {
    Session::builder().map_err(|e| anyhow!("{e}"))?.commit_from_file(model).map_err(|e| anyhow!("cannot load the model: {e}"))
}

impl Embedder {
    /// Load the model. `root/model_cache` keeps a download if the cache of Hugging Face does not have the model.
    /// The model runs on the GPU (DirectML) if it can, else on the CPU. RINRIKUN_EMBED=cpu selects the CPU.
    pub fn load(root: &Path) -> Result<Embedder> {
        let folder = match cached_model() {
            Some(folder) => folder,
            None => {
                let folder = root.join("model_cache").join(MODEL.replace('/', "--"));
                download_model(&folder)?;
                folder
            }
        };
        let mut tokenizer = Tokenizer::from_file(folder.join("tokenizer.json")).map_err(|e| anyhow!("cannot read the tokenizer: {e}"))?;
        tokenizer
            .with_truncation(Some(tokenizers::TruncationParams { max_length: MAX_TOKENS, ..Default::default() }))
            .map_err(|e| anyhow!("cannot set the truncation: {e}"))?;
        let model = folder.join(MODEL_FILE);
        let (session, device) = if std::env::var("RINRIKUN_EMBED").is_ok_and(|v| v.eq_ignore_ascii_case("cpu")) {
            (cpu_session(&model)?, "the CPU (RINRIKUN_EMBED=cpu)".to_string())
        } else {
            match gpu_session(&model) {
                Ok(session) => (session, "the GPU (DirectML)".to_string()),
                Err(error) => {
                    eprintln!("WARNING the GPU is not usable for the embeddings ({error:#}): the CPU computes them");
                    (cpu_session(&model)?, "the CPU".to_string())
                }
            }
        };
        println!("the embeddings run on {device}");
        let extra = session
            .inputs()
            .iter()
            .filter(|i| i.name() != "input_ids" && i.name() != "attention_mask")
            .map(|i| {
                let shape = match i.dtype() {
                    ValueType::Tensor { shape, .. } => shape.iter().map(|&d| d.max(0)).collect(),
                    _ => Vec::new(),
                };
                (i.name().to_string(), shape)
            })
            .collect();
        Ok(Embedder { tokenizer, session, extra })
    }

    /// The token ids of a text, with the prompt and the special tokens
    pub fn tokens(&self, text: &str) -> Result<Vec<i64>> {
        let encoding = self.tokenizer.encode(format!("{PROMPT}{text}"), true).map_err(|e| anyhow!("cannot tokenize: {e}"))?;
        Ok(encoding.get_ids().iter().map(|&id| id as i64).collect())
    }

    /// `embed_texts`: the vector of each text. Texts of similar length go in the same batch, so
    /// that the padding is small.
    pub fn embed(&mut self, texts: &[String]) -> Result<Vec<Vec<f32>>> {
        let encoded: Vec<Vec<i64>> = texts.iter().map(|t| self.tokens(t)).collect::<Result<_>>()?;
        let mut order: Vec<usize> = (0..texts.len()).collect();
        order.sort_by_key(|&i| encoded[i].len());
        let mut out = vec![Vec::new(); texts.len()];
        for batch in order.chunks(BATCH_SIZE) {
            let width = batch.iter().map(|&i| encoded[i].len()).max().unwrap_or(0);
            let mut ids = vec![0i64; batch.len() * width];
            let mut mask = vec![0i64; batch.len() * width];
            for (row, &i) in batch.iter().enumerate() {
                for (k, &id) in encoded[i].iter().enumerate() {
                    ids[row * width + k] = id;
                    mask[row * width + k] = 1;
                }
            }
            let shape = vec![batch.len() as i64, width as i64];
            let mut inputs: Vec<(String, ort::value::DynValue)> = vec![
                ("input_ids".into(), Tensor::from_array((shape.clone(), ids)).map_err(|e| anyhow!("{e}"))?.into_dyn()),
                ("attention_mask".into(), Tensor::from_array((shape, mask)).map_err(|e| anyhow!("{e}"))?.into_dyn()),
            ];
            for (name, shape) in &self.extra {
                let size = shape.iter().product::<i64>().max(0) as usize;
                inputs.push((name.clone(), Tensor::from_array((shape.clone(), vec![0f32; size])).map_err(|e| anyhow!("{e}"))?.into_dyn()));
            }
            let outputs = self.session.run(inputs).map_err(|e| anyhow!("the model failed: {e}"))?;
            let (out_shape, values) = outputs["sentence_embedding"].try_extract_tensor::<f32>().map_err(|e| anyhow!("{e}"))?;
            if out_shape.len() != 2 || out_shape[1] as usize != DIM {
                bail!("the model gave vectors of the shape {out_shape:?}");
            }
            for (row, &i) in batch.iter().enumerate() {
                out[i] = values[row * DIM..(row + 1) * DIM].to_vec();
            }
        }
        Ok(out)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn the_text_and_its_hash_have_the_old_format() {
        let row = json!({"title": "Show 12", "title_native": "ショー", "year": 2022, "genres": ["Action", "Drama"],
                         "tags": ["A", "B"], "studios": ["Studio 5"], "overview": "An invented show."});
        let r = row.as_object().unwrap();
        assert_eq!(build_text(r), "ショー (Show 12). 2022. Genres: Action, Drama. Tags: A, B. Studios: Studio 5. An invented show.");
        let empty = json!({"title": "X", "title_native": "", "year": null, "genres": [], "tags": [], "studios": [], "overview": ""});
        assert_eq!(build_text(empty.as_object().unwrap()), "X (X)");
        // hashlib.sha1(f"{MODEL}\n{PROMPT}\nX (X)".encode()).hexdigest() in Python
        assert_eq!(text_hash(empty.as_object().unwrap()), sha1_smol::Sha1::from(format!("{MODEL}\n{PROMPT}\nX (X)")).digest().to_string());
    }
}

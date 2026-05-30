#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::{
    fs::{self, OpenOptions},
    io::{Read, Write},
    net::{SocketAddr, TcpStream},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

const API_HOST: &str = "127.0.0.1";
const API_PORT: u16 = 8765;
const CANONICAL_REPO_PATH: &str = "/Users/dianeposs/Desktop/Jordan/meme_trader_pro";

#[derive(Serialize)]
struct ApiLaunchStatus {
    running: bool,
    started: bool,
    detail: String,
    api_token: Option<String>,
}

#[derive(Deserialize)]
struct SessionFile {
    token: Option<String>,
    process_id: Option<u32>,
    started_at: Option<f64>,
}

#[derive(Debug, Deserialize, PartialEq)]
struct HealthSession {
    process_id: Option<u32>,
    session_started_at: Option<f64>,
}

fn session_file(repo_root: &Path) -> PathBuf {
    repo_root.join("data").join("desktop_api_session.json")
}

fn read_session_file(repo_root: &Path) -> Option<SessionFile> {
    let contents = fs::read_to_string(session_file(repo_root)).ok()?;
    serde_json::from_str(&contents).ok()
}

fn generate_api_token() -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or(0);
    format!("mtp-{}-{}", std::process::id(), nanos)
}

fn find_repo_root(start: &Path) -> Result<PathBuf, String> {
    let mut current = if start.is_file() {
        start.parent().unwrap_or(start).to_path_buf()
    } else {
        start.to_path_buf()
    };
    loop {
        if current.join("desktop_api.py").exists() && current.join("trading_env").exists() {
            return Ok(current);
        }
        if !current.pop() {
            break;
        }
    }
    Err(format!("could not find MemeTraderPro repo root from {}", start.display()))
}

fn desktop_api_command_args(repo_root: &Path) -> Result<(PathBuf, Vec<String>), String> {
    let script = repo_root.join("desktop_api.py");
    if !script.exists() {
        return Err(format!("desktop_api.py missing at {}", script.display()));
    }

    let venv_python = repo_root.join("trading_env").join("bin").join("python");
    let python = if venv_python.exists() {
        venv_python
    } else {
        PathBuf::from("python3")
    };

    Ok((
        PathBuf::from("/usr/bin/env"),
        vec![
            "PYTHONUNBUFFERED=1".to_string(),
            python.display().to_string(),
            script.display().to_string(),
            "--host".to_string(),
            API_HOST.to_string(),
            "--port".to_string(),
            API_PORT.to_string(),
        ],
    ))
}

fn parse_http_body(response: &str) -> &str {
    response.split_once("\r\n\r\n").map(|(_, body)| body).unwrap_or("")
}

fn parse_health_session(response: &str) -> Option<HealthSession> {
    if !response.contains("200 OK") || !response.contains("EXECUTION_LOCKED") {
        return None;
    }
    serde_json::from_str(parse_http_body(response)).ok()
}

fn session_matches_health(session: &SessionFile, health: &HealthSession) -> bool {
    session.token.as_ref().is_some_and(|token| !token.is_empty())
        && session.process_id == health.process_id
        && session.started_at == health.session_started_at
}

fn api_health_session() -> Option<HealthSession> {
    let address: SocketAddr = match format!("{API_HOST}:{API_PORT}").parse() {
        Ok(address) => address,
        Err(_) => return None,
    };
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(350)) else {
        return None;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
    let request = b"GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n";
    if stream.write_all(request).is_err() {
        return None;
    }
    let mut response = String::new();
    if stream.read_to_string(&mut response).is_err() {
        return None;
    }
    parse_health_session(&response)
}

fn api_health_ok() -> bool {
    api_health_session().is_some()
}

fn local_repo_root() -> Result<PathBuf, String> {
    if let Ok(root) = std::env::var("MTP_REPO_ROOT") {
        let candidate = PathBuf::from(root);
        if candidate.join("desktop_api.py").exists() && candidate.join("trading_env").exists() {
            return Ok(candidate);
        }
    }

    let canonical = PathBuf::from(CANONICAL_REPO_PATH);
    if canonical.join("desktop_api.py").exists() && canonical.join("trading_env").exists() {
        return Ok(canonical);
    }

    if let Ok(root) = find_repo_root(Path::new(env!("CARGO_MANIFEST_DIR"))) {
        return Ok(root);
    }
    let exe = std::env::current_exe().map_err(|error| format!("current executable unavailable: {error}"))?;
    find_repo_root(&exe)
}

fn terminate_process(process_id: u32) {
    let _ = Command::new("/bin/kill")
        .arg(process_id.to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
}

fn wait_for_api_shutdown() {
    for _ in 0..20 {
        if api_health_session().is_none() {
            return;
        }
        thread::sleep(Duration::from_millis(100));
    }
}

fn spawn_desktop_api(repo_root: &Path, api_token: &str) -> Result<(), String> {
    fs::create_dir_all(repo_root.join("logs")).map_err(|error| format!("cannot create logs directory: {error}"))?;
    let log_path = repo_root.join("logs").join("desktop_api_tauri.log");
    let stdout = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .map_err(|error| format!("cannot open desktop API log: {error}"))?;
    let stderr = stdout
        .try_clone()
        .map_err(|error| format!("cannot clone desktop API log handle: {error}"))?;
    let (python, args) = desktop_api_command_args(repo_root)?;
    Command::new(python)
        .args(args)
        .env("MTP_DESKTOP_API_TOKEN", api_token)
        .current_dir(repo_root)
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr))
        .spawn()
        .map_err(|error| format!("failed to start desktop API: {error}"))?;
    Ok(())
}

#[tauri::command]
fn ensure_desktop_api() -> ApiLaunchStatus {
    let repo_root = match local_repo_root() {
        Ok(root) => root,
        Err(error) => {
            return ApiLaunchStatus {
                running: false,
                started: false,
                detail: error,
                api_token: None,
            }
        }
    };

    if let Some(health) = api_health_session() {
        let session = read_session_file(&repo_root);
        let api_token = session
            .as_ref()
            .filter(|session| session_matches_health(session, &health))
            .and_then(|session| session.token.clone());
        if api_token.is_some() {
            return ApiLaunchStatus {
                running: true,
                started: false,
                detail: "desktop API already running with matching session".to_string(),
                api_token,
            };
        }

        if let Some(process_id) = health.process_id {
            terminate_process(process_id);
            wait_for_api_shutdown();
        }
    }

    let api_token = generate_api_token();

    if let Err(error) = spawn_desktop_api(&repo_root, &api_token) {
        return ApiLaunchStatus {
            running: false,
            started: false,
            detail: error,
            api_token: None,
        };
    }

    for _ in 0..20 {
        thread::sleep(Duration::from_millis(250));
        if api_health_ok() {
            return ApiLaunchStatus {
                running: true,
                started: true,
                detail: "started local read-only desktop API".to_string(),
                api_token: Some(api_token),
            };
        }
    }

    ApiLaunchStatus {
        running: false,
        started: true,
        detail: "desktop API was started but did not become healthy yet".to_string(),
        api_token: None,
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![ensure_desktop_api])
        .run(tauri::generate_context!())
        .expect("error while running MemeTraderPro desktop shell");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn repo_root_finder_finds_desktop_api() {
        let start = Path::new(env!("CARGO_MANIFEST_DIR"));
        let root = find_repo_root(start).expect("repo root");

        assert!(root.join("desktop_api.py").exists());
        assert!(root.join("trading_env").exists());
    }

    #[test]
    fn local_repo_root_prefers_canonical_project_path() {
        let root = local_repo_root().expect("repo root");

        assert!(root.ends_with("meme_trader_pro"));
        assert!(!root.to_string_lossy().contains("Jordan 2"));
    }

    #[test]
    fn desktop_api_command_targets_read_only_server() {
        let root = find_repo_root(Path::new(env!("CARGO_MANIFEST_DIR"))).expect("repo root");
        let (_python, args) = desktop_api_command_args(&root).expect("command args");
        let joined = args.join(" ");

        assert!(joined.contains("desktop_api.py"));
        assert!(joined.contains("--host 127.0.0.1"));
        assert!(joined.contains("--port 8765"));
        assert!(!joined.contains("--api-token"));
        assert!(!joined.contains("paper_trader.py"));
        assert!(!joined.contains("execution"));
        assert!(!joined.contains("rug_watchdog"));
    }

    #[test]
    fn health_session_parser_extracts_running_process_identity() {
        let response = concat!(
            "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n",
            "{\"mode\":\"EXECUTION_LOCKED\",\"process_id\":123,\"session_started_at\":456.5}"
        );

        let health = parse_health_session(response).expect("health identity");

        assert_eq!(health.process_id, Some(123));
        assert_eq!(health.session_started_at, Some(456.5));
    }

    #[test]
    fn session_token_must_match_running_process_identity() {
        let health = HealthSession {
            process_id: Some(123),
            session_started_at: Some(456.5),
        };
        let matching = SessionFile {
            token: Some("token".to_string()),
            process_id: Some(123),
            started_at: Some(456.5),
        };
        let stale = SessionFile {
            token: Some("token".to_string()),
            process_id: Some(999),
            started_at: Some(456.5),
        };

        assert!(session_matches_health(&matching, &health));
        assert!(!session_matches_health(&stale, &health));
    }
}

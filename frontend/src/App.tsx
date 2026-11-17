import { useCallback, useEffect, useState, type FormEvent } from "react";

type User = {
  id: string;
  username: string;
  display_name: string;
  email: string;
};

type Video = {
  id: string;
  title: string;
  description: string | null;
  channel_name: string;
  channel_handle: string;
  created_at: string;
  file_size_bytes: number | null;
  playback_url: string;
};

type AuthResponse = {
  access_token: string;
  user: User;
};

const API = "/api/v1";

async function api<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `Request failed: ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export default function App() {
  const [videos, setVideos] = useState<Video[]>([]);
  const [selected, setSelected] = useState<Video | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [showAuth, setShowAuth] = useState(false);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);

  const loadVideos = useCallback(async (search = "") => {
    try {
      const params = new URLSearchParams();
      if (search.trim()) params.set("q", search.trim());
      const result = await api<{ items: Video[]; total: number }>(`/videos?${params.toString()}`);
      setVideos(result.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить видео");
    }
  }, []);

  useEffect(() => {
    void loadVideos();
    api<AuthResponse>("/auth/refresh", { method: "POST" })
      .then((result) => {
        setToken(result.access_token);
        setUser(result.user);
      })
      .catch(() => undefined);
  }, [loadVideos]);

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    const payload =
      authMode === "register"
        ? {
            email: String(data.get("email")),
            username: String(data.get("username")),
            display_name: String(data.get("display_name")),
            password: String(data.get("password")),
          }
        : {
            identifier: String(data.get("identifier")),
            password: String(data.get("password")),
          };
    try {
      const result = await api<AuthResponse>(
        authMode === "register" ? "/auth/register" : "/auth/login",
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) },
      );
      setToken(result.access_token);
      setUser(result.user);
      setShowAuth(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка авторизации");
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    try {
      await api<void>("/auth/logout", { method: "POST" });
    } finally {
      setToken(null);
      setUser(null);
      setUploadOpen(false);
    }
  }

  async function submitUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    setBusy(true);
    setError("");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      await api<Video>("/videos/upload", { method: "POST", body: form }, token);
      setUploadOpen(false);
      formElement.reset();
      await loadVideos(query);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить видео");
    } finally {
      setBusy(false);
    }
  }

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSelected(null);
    void loadVideos(query);
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <button className="brand" onClick={() => { setSelected(null); void loadVideos(); }}>
          <span className="brand-mark">▶</span><span>YouTube<span className="brand-light"> Clone</span></span>
        </button>
        <form className="search" onSubmit={search}>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск видео" aria-label="Поиск видео" />
          <button type="submit" aria-label="Найти">⌕</button>
        </form>
        <div className="account-actions">
          {user ? (
            <>
              <span className="user-label">{user.display_name}</span>
              <button className="outline-button" onClick={() => setUploadOpen(true)}>＋ Загрузить</button>
              <button className="icon-button" onClick={() => void logout()} title="Выйти">↗</button>
            </>
          ) : (
            <button className="outline-button" onClick={() => { setShowAuth(true); setError(""); }}>Войти</button>
          )}
        </div>
      </header>

      <main className="page">
        {error && <div className="error-banner">{error}<button onClick={() => setError("")}>×</button></div>}
        {selected ? (
          <section className="watch-layout">
            <button className="back-link" onClick={() => setSelected(null)}>← Назад к видео</button>
            <video className="player" src={selected.playback_url} controls autoPlay playsInline />
            <h1>{selected.title}</h1>
            <div className="video-meta">{selected.channel_name} · @{selected.channel_handle}</div>
            {selected.description && <p className="description">{selected.description}</p>}
          </section>
        ) : (
          <>
            <div className="section-heading">
              <div><p className="eyebrow">СМОТРИ И ДЕЛИСЬ</p><h1>Видео для тебя</h1></div>
              <span className="result-count">{videos.length} видео</span>
            </div>
            {videos.length ? (
              <div className="video-grid">
                {videos.map((video) => (
                  <button className="video-card" key={video.id} onClick={() => setSelected(video)}>
                    <div className="thumbnail"><span className="play-icon">▶</span><span className="duration-label">PLAY</span></div>
                    <div className="video-card-info">
                      <div className="channel-avatar">{video.channel_name.slice(0, 1).toUpperCase()}</div>
                      <div><h2>{video.title}</h2><p>{video.channel_name}</p><p>{new Date(video.created_at).toLocaleDateString("ru-RU")}</p></div>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="empty-state">
                <div className="empty-icon">▷</div>
                <h2>Пока здесь нет видео</h2>
                <p>Войди в аккаунт и загрузи первое видео на платформу.</p>
                {!user && <button className="primary-button" onClick={() => setShowAuth(true)}>Создать аккаунт</button>}
              </div>
            )}
          </>
        )}
      </main>

      {showAuth && (
        <div className="modal-backdrop" onClick={() => setShowAuth(false)}>
          <section className="modal" onClick={(event) => event.stopPropagation()}>
            <button className="modal-close" onClick={() => setShowAuth(false)}>×</button>
            <span className="brand-mark large">▶</span>
            <h2>{authMode === "login" ? "С возвращением" : "Создать аккаунт"}</h2>
            <p className="muted">Войди, чтобы публиковать видео и управлять каналом.</p>
            <form className="stack-form" onSubmit={submitAuth}>
              {authMode === "register" ? (
                <>
                  <input name="email" type="email" placeholder="Email" required />
                  <input name="username" placeholder="Имя пользователя" minLength={3} maxLength={30} required />
                  <input name="display_name" placeholder="Отображаемое имя" maxLength={80} required />
                </>
              ) : <input name="identifier" placeholder="Email или имя пользователя" required />}
              <input name="password" type="password" placeholder="Пароль (минимум 8 символов)" minLength={8} required />
              <button className="primary-button" disabled={busy}>{busy ? "Подождите..." : authMode === "login" ? "Войти" : "Зарегистрироваться"}</button>
            </form>
            <button className="switch-mode" onClick={() => setAuthMode(authMode === "login" ? "register" : "login")}>
              {authMode === "login" ? "Нет аккаунта? Зарегистрироваться" : "Уже есть аккаунт? Войти"}
            </button>
          </section>
        </div>
      )}

      {uploadOpen && (
        <div className="modal-backdrop" onClick={() => setUploadOpen(false)}>
          <section className="modal" onClick={(event) => event.stopPropagation()}>
            <button className="modal-close" onClick={() => setUploadOpen(false)}>×</button>
            <h2>Загрузить видео</h2>
            <p className="muted">MP4, WebM или MOV · до 500 МБ</p>
            <form className="stack-form" onSubmit={submitUpload}>
              <input name="title" placeholder="Название видео" maxLength={120} required />
              <textarea name="description" placeholder="Описание (необязательно)" rows={4} />
              <label className="file-picker">Выбрать видео<input name="file" type="file" accept="video/mp4,video/webm,video/quicktime" required /></label>
              <button className="primary-button" disabled={busy}>{busy ? "Загрузка..." : "Опубликовать"}</button>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}

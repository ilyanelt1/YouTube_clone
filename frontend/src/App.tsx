import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

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
  status: string;
  visibility: "public" | "unlisted" | "private";
  channel_name: string;
  channel_handle: string;
  created_at: string;
  file_size_bytes: number | null;
  mime_type: string | null;
  playback_url: string;
  thumbnail_url: string | null;
};

type Engagement = { likes: number; dislikes: number; comments: number; shares: number; reposts: number; viewer_reposted: boolean; views: number; viewer_reaction: "like" | "dislike" | null };

type SocialComment = { id: string; video_id: string; parent_id: string | null; body: string; author_name: string; author_handle: string; created_at: string; updated_at: string };

type AuthResponse = {
  access_token: string;
  user: User;
};

const API = "/api/v1";
const MAX_VIDEO_SIZE = 500 * 1024 * 1024;
const MAX_THUMBNAIL_SIZE = 5 * 1024 * 1024;

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

function uploadWithProgress(
  form: FormData,
  token: string,
  onProgress: (value: number) => void,
): Promise<Video> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", `${API}/videos/upload`);
    request.withCredentials = true;
    request.setRequestHeader("Authorization", `Bearer ${token}`);
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)));
      }
    };
    request.onload = () => {
      const payload = JSON.parse(request.responseText || "{}");
      if (request.status >= 200 && request.status < 300) {
        resolve(payload as Video);
      } else {
        reject(new Error(payload.detail ?? `Upload failed: ${request.status}`));
      }
    };
    request.onerror = () => reject(new Error("Network error while uploading video"));
    request.onabort = () => reject(new Error("Upload cancelled"));
    request.send(form);
  });
}

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function App() {
  const [videos, setVideos] = useState<Video[]>([]);
  const [myVideos, setMyVideos] = useState<Video[]>([]);
  const [selected, setSelected] = useState<Video | null>(null);
  const [engagement, setEngagement] = useState<Engagement | null>(null);
  const [comments, setComments] = useState<SocialComment[]>([]);
  const [commentDraft, setCommentDraft] = useState("");
  const [replyTo, setReplyTo] = useState<SocialComment | null>(null);
  const [subscribed, setSubscribed] = useState(false);
  const [subscriberCount, setSubscriberCount] = useState(0);
  const viewedVideoIds = useRef(new Set<string>());
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [showAuth, setShowAuth] = useState(false);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [showLibrary, setShowLibrary] = useState(false);
  const [editingVideo, setEditingVideo] = useState<Video | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editVisibility, setEditVisibility] = useState<Video["visibility"]>("public");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedThumbnail, setSelectedThumbnail] = useState<File | null>(null);

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

  const loadMyVideos = useCallback(async (accessToken: string) => {
    const result = await api<{ items: Video[]; total: number }>("/videos/mine", {}, accessToken);
    setMyVideos(result.items);
  }, []);

  useEffect(() => {
    void loadVideos();
    api<AuthResponse>("/auth/refresh", { method: "POST" })
      .then((result) => {
        setToken(result.access_token);
        setUser(result.user);
        void loadMyVideos(result.access_token).catch(() => undefined);
      })
      .catch(() => undefined);
  }, [loadVideos, loadMyVideos]);

  useEffect(() => {
    if (!selected) {
      setEngagement(null);
      setComments([]);
      setReplyTo(null);
      return;
    }
    let active = true;
    void Promise.all([
      api<Engagement>(`/videos/${selected.id}/engagement`, {}, token ?? undefined),
      api<{ items: SocialComment[]; total: number }>(`/videos/${selected.id}/comments`, {}, token ?? undefined),
      api<{ subscribed: boolean; subscribers: number }>(`/channels/${encodeURIComponent(selected.channel_handle)}/subscription`, {}, token ?? undefined),
    ]).then(([stats, discussion, subscription]) => {
      if (!active) return;
      setEngagement(stats);
      setComments(discussion.items);
      setSubscribed(subscription.subscribed);
      setSubscriberCount(subscription.subscribers);
    }).catch((err) => {
      if (active) setError(err instanceof Error ? err.message : "Не удалось загрузить реакции и комментарии");
    });
    if (!viewedVideoIds.current.has(selected.id)) {
      viewedVideoIds.current.add(selected.id);
      void api<{ views: number }>(`/videos/${selected.id}/view`, { method: "POST" }, token ?? undefined)
        .then((result) => { if (active) setEngagement((current) => current ? { ...current, views: result.views } : current); })
        .catch(() => undefined);
    }
    return () => { active = false; };
  }, [selected?.id, token, user?.id]);

  useEffect(() => {
    const videoId = new URLSearchParams(window.location.search).get("video");
    if (!videoId) return;
    api<Video>(`/videos/${videoId}`)
      .then(setSelected)
      .catch(() => setError("Видео по ссылке не найдено или недоступно"));
  }, []);

  async function setVideoReaction(reaction: "like" | "dislike") {
    if (!selected) return;
    if (!token) { setShowAuth(true); return; }
    try {
      const next = engagement?.viewer_reaction === reaction ? null : reaction;
      const result = await api<Engagement>(`/videos/${selected.id}/reaction`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reaction: next }),
      }, token);
      setEngagement(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить реакцию");
    }
  }

  async function submitComment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || !token || !commentDraft.trim()) {
      if (!token) setShowAuth(true);
      return;
    }
    try {
      const created = await api<SocialComment>(`/videos/${selected.id}/comments`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: commentDraft.trim(), parent_id: replyTo?.id ?? null }),
      }, token);
      setComments((current) => [...current, created]);
      setCommentDraft("");
      setReplyTo(null);
      setEngagement((current) => current ? { ...current, comments: current.comments + 1 } : current);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось отправить комментарий");
    }
  }

  async function editComment(comment: SocialComment) {
    if (!token) return;
    const body = window.prompt("Изменить комментарий", comment.body);
    if (body === null || !body.trim()) return;
    try {
      const updated = await api<SocialComment>(`/comments/${comment.id}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: body.trim() }),
      }, token);
      setComments((current) => current.map((item) => item.id === comment.id ? updated : item));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось изменить комментарий");
    }
  }

  async function removeComment(comment: SocialComment) {
    if (!token) return;
    try {
      await api<void>(`/comments/${comment.id}`, { method: "DELETE" }, token);
      const removedCount = comments.filter((item) => item.id === comment.id || item.parent_id === comment.id).length;
      setComments((current) => current.filter((item) => item.id !== comment.id && item.parent_id !== comment.id));
      setEngagement((current) => current ? { ...current, comments: Math.max(0, current.comments - removedCount) } : current);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось удалить комментарий");
    }
  }

  async function toggleRepost() {
    if (!selected) return;
    if (!token) { setShowAuth(true); return; }
    try {
      const method = engagement?.viewer_reposted ? "DELETE" : "PUT";
      const result = await api<Engagement>(`/videos/${selected.id}/repost`, { method }, token);
      setEngagement(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сделать репост");
    }
  }

  async function toggleSubscription() {
    if (!selected) return;
    if (!token) { setShowAuth(true); return; }
    try {
      const method = subscribed ? "DELETE" : "PUT";
      const result = await api<{ subscribed: boolean; subscribers: number }>(
        `/channels/${encodeURIComponent(selected.channel_handle)}/subscription`, { method }, token,
      );
      setSubscribed(result.subscribed);
      setSubscriberCount(result.subscribers);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось изменить подписку");
    }
  }

  async function shareVideo() {
    if (!selected) return;
    try {
      if (token) {
        const result = await api<{ shares: number; share_url: string }>(
          `/videos/${selected.id}/share`, { method: "POST" }, token,
        );
        setEngagement((current) => current ? { ...current, shares: result.shares } : current);
        if (navigator.share) await navigator.share({ title: selected.title, url: result.share_url });
        else await navigator.clipboard.writeText(result.share_url);
      } else {
        const url = `${window.location.origin}/?video=${selected.id}`;
        if (navigator.share) await navigator.share({ title: selected.title, url });
        else await navigator.clipboard.writeText(url);
      }
    } catch (err) {
      if (err instanceof Error && err.name !== "AbortError") setError("Не удалось поделиться видео");
    }
  }

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
      await loadMyVideos(result.access_token);
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
      setMyVideos([]);
      setUploadOpen(false);
      setShowLibrary(false);
    }
  }

  async function submitUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    if (!selectedFile) {
      setError("Выбери видеофайл для загрузки");
      return;
    }
    if (!["video/mp4", "video/webm", "video/quicktime"].includes(selectedFile.type)) {
      setError("Поддерживаются только MP4, WebM и MOV");
      return;
    }
    if (selectedFile.size > MAX_VIDEO_SIZE) {
      setError("Размер видео не должен превышать 500 МБ");
      return;
    }
    if (selectedThumbnail && selectedThumbnail.size > MAX_THUMBNAIL_SIZE) {
      setError("Размер обложки не должен превышать 5 МБ");
      return;
    }

    setBusy(true);
    setUploadProgress(0);
    setError("");
    const form = new FormData(event.currentTarget);
    if (!selectedThumbnail) form.delete("thumbnail");
    try {
      await uploadWithProgress(form, token, setUploadProgress);
      setUploadOpen(false);
      setSelectedFile(null);
      setSelectedThumbnail(null);
      setUploadProgress(null);
      await Promise.all([loadVideos(query), loadMyVideos(token)]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить видео");
      setUploadProgress(null);
    } finally {
      setBusy(false);
    }
  }

  function openEditor(video: Video) {
    setEditingVideo(video);
    setEditTitle(video.title);
    setEditDescription(video.description ?? "");
    setEditVisibility(video.visibility);
  }

  async function saveVideo(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !editingVideo) return;
    setBusy(true);
    setError("");
    try {
      await api<Video>(
        `/videos/${editingVideo.id}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: editTitle,
            description: editDescription,
            visibility: editVisibility,
          }),
        },
        token,
      );
      setEditingVideo(null);
      await Promise.all([loadVideos(query), loadMyVideos(token)]);
      if (selected?.id === editingVideo.id) {
        const updated = await api<Video>(`/videos/${editingVideo.id}`, {}, token);
        setSelected(updated);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить изменения");
    } finally {
      setBusy(false);
    }
  }

  async function removeVideo(video: Video) {
    if (!token || !window.confirm(`Удалить видео «${video.title}»? Это действие нельзя отменить.`)) return;
    setBusy(true);
    setError("");
    try {
      await api<void>(`/videos/${video.id}`, { method: "DELETE" }, token);
      if (selected?.id === video.id) setSelected(null);
      await Promise.all([loadVideos(query), loadMyVideos(token)]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось удалить видео");
    } finally {
      setBusy(false);
    }
  }

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSelected(null);
    setShowLibrary(false);
    void loadVideos(query);
  }

  function closeUpload() {
    if (busy) return;
    setUploadOpen(false);
    setUploadProgress(null);
    setSelectedFile(null);
    setSelectedThumbnail(null);
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <button className="brand" onClick={() => { setSelected(null); setShowLibrary(false); void loadVideos(); }}>
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
              <button className="outline-button" onClick={() => { setShowLibrary(true); setSelected(null); }}>Мои видео</button>
              <button className="outline-button" onClick={() => { setUploadOpen(true); setError(""); }}>＋ Загрузить</button>
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
            <button className="back-link" onClick={() => setSelected(null)}>← Назад</button>
            <video className="player" src={selected.playback_url} controls autoPlay playsInline />
            <h1>{selected.title}</h1>
            <div className="video-meta">{selected.channel_name} · @{selected.channel_handle} · {new Date(selected.created_at).toLocaleDateString("ru-RU")}</div>
            {selected.description && <p className="description">{selected.description}</p>}
            <div className="social-toolbar">
              <div className="reaction-group">
                <button className={engagement?.viewer_reaction === "like" ? "social-button active" : "social-button"} onClick={() => void setVideoReaction("like")} aria-label="Нравится">👍 {engagement?.likes ?? 0}</button>
                <button className={engagement?.viewer_reaction === "dislike" ? "social-button active" : "social-button"} onClick={() => void setVideoReaction("dislike")} aria-label="Не нравится">👎 {engagement?.dislikes ?? 0}</button>
              </div>
              <button className={engagement?.viewer_reposted ? "social-button active" : "social-button"} onClick={() => void toggleRepost()}>🔁 Репост · {engagement?.reposts ?? 0}</button>
              <button className="social-button" onClick={() => void shareVideo()}>↗ Поделиться · {engagement?.shares ?? 0}</button>
              <span className="social-muted">◉ {engagement?.views ?? 0} просмотров</span>
            </div>
            {user && user.username !== selected.channel_handle && (
              <div className="channel-subscription">
                <div><strong>{selected.channel_name}</strong><span>{subscriberCount} подписчиков</span></div>
                <button className={subscribed ? "outline-button subscribed" : "primary-button"} onClick={() => void toggleSubscription()}>
                  {subscribed ? "Вы подписаны" : "Подписаться"}
                </button>
              </div>
            )}
            <section className="comments-section">
              <h2>Комментарии · {engagement?.comments ?? comments.length}</h2>
              <form className="comment-form" onSubmit={submitComment}>
                {replyTo && <div className="replying-to">Ответ пользователю @{replyTo.author_handle}<button type="button" onClick={() => setReplyTo(null)}>Отмена</button></div>}
                <textarea value={commentDraft} onChange={(event) => setCommentDraft(event.target.value)} placeholder={user ? "Оставьте комментарий..." : "Войдите, чтобы оставить комментарий"} maxLength={2000} rows={3} />
                <button className="primary-button" disabled={!commentDraft.trim()}>Отправить</button>
              </form>
              <div className="comment-list">
                {comments.map((comment) => (
                  <article className={comment.parent_id ? "comment reply-comment" : "comment"} key={comment.id}>
                    <div className="comment-avatar">{comment.author_name.slice(0, 1).toUpperCase()}</div>
                    <div className="comment-content">
                      <div className="comment-author">{comment.author_name} <span>@{comment.author_handle} · {new Date(comment.created_at).toLocaleDateString("ru-RU")}</span></div>
                      <p>{comment.body}</p>
                      <div className="comment-actions">
                        {!comment.parent_id && <button onClick={() => { setReplyTo(comment); setCommentDraft(""); }}>Ответить</button>}
                        {(user?.username === comment.author_handle || user?.username === selected.channel_handle) && <button onClick={() => void removeComment(comment)}>Удалить</button>}
                        {user?.username === comment.author_handle && <button onClick={() => void editComment(comment)}>Изменить</button>}
                      </div>
                    </div>
                  </article>
                ))}
                {!comments.length && <p className="comments-empty">Пока нет комментариев. Будьте первым!</p>}
              </div>
            </section>
          </section>
        ) : showLibrary ? (
          <>
            <div className="section-heading">
              <div><p className="eyebrow">ТВОЙ КАНАЛ</p><h1>Мои видео</h1></div>
              <span className="result-count">{myVideos.length} видео</span>
            </div>
            {myVideos.length ? (
              <div className="video-grid">
                {myVideos.map((video) => (
                  <article className="video-card managed-video" key={video.id}>
                    <button className="video-card-open" onClick={() => setSelected(video)}>
                      <div className="thumbnail">
                        {video.thumbnail_url ? <img src={video.thumbnail_url} alt="" /> : <span className="play-icon">▶</span>}
                      </div>
                      <div className="video-card-info">
                        <div className="channel-avatar">{video.title.slice(0, 1).toUpperCase()}</div>
                        <div><h2>{video.title}</h2><p>{video.visibility === "public" ? "Открытый доступ" : video.visibility === "unlisted" ? "Доступ по ссылке" : "Приватное"}</p><p>{formatSize(video.file_size_bytes ?? 0)}</p></div>
                      </div>
                    </button>
                    <div className="video-actions">
                      <button className="small-button" onClick={() => openEditor(video)}>Изменить</button>
                      <button className="small-button danger-button" disabled={busy} onClick={() => void removeVideo(video)}>Удалить</button>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="empty-state"><div className="empty-icon">▷</div><h2>Ты ещё не загрузил видео</h2><p>Загруженные ролики появятся здесь.</p><button className="primary-button" onClick={() => setUploadOpen(true)}>Загрузить первое видео</button></div>
            )}
          </>
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
                    <div className="thumbnail">
                      {video.thumbnail_url ? <img src={video.thumbnail_url} alt="" /> : <span className="play-icon">▶</span>}
                    </div>
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
        <div className="modal-backdrop" onClick={closeUpload}>
          <section className="modal upload-modal" onClick={(event) => event.stopPropagation()}>
            <button className="modal-close" onClick={closeUpload}>×</button>
            <h2>Загрузить видео</h2>
            <p className="muted">MP4, WebM или MOV · до 500 МБ. Обложка — JPEG, PNG или WebP до 5 МБ.</p>
            <form className="stack-form" onSubmit={submitUpload}>
              <input name="title" placeholder="Название видео" maxLength={120} required />
              <textarea name="description" placeholder="Описание видео" rows={4} maxLength={5000} />
              <label className="field-label">Кто сможет смотреть?
                <select name="visibility" defaultValue="public">
                  <option value="public">Открытый доступ — в общем каталоге</option>
                  <option value="unlisted">Доступ по ссылке — скрыто из каталога</option>
                  <option value="private">Приватное — только владелец</option>
                </select>
              </label>
              <label className="file-picker">Выбрать видеофайл
                <input name="file" type="file" accept="video/mp4,video/webm,video/quicktime" required onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)} />
                {selectedFile && <span className="file-info">{selectedFile.name} · {formatSize(selectedFile.size)}</span>}
              </label>
              <label className="file-picker">Обложка (необязательно)
                <input name="thumbnail" type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setSelectedThumbnail(event.target.files?.[0] ?? null)} />
                {selectedThumbnail && <span className="file-info">{selectedThumbnail.name} · {formatSize(selectedThumbnail.size)}</span>}
              </label>
              {uploadProgress !== null && (
                <div className="upload-progress">
                  <div className="progress-heading"><span>Загрузка файла</span><strong>{uploadProgress}%</strong></div>
                  <progress value={uploadProgress} max="100" />
                </div>
              )}
              <button className="primary-button" disabled={busy}>{busy ? "Загрузка..." : "Опубликовать видео"}</button>
            </form>
          </section>
        </div>
      )}

      {editingVideo && (
        <div className="modal-backdrop" onClick={() => !busy && setEditingVideo(null)}>
          <section className="modal" onClick={(event) => event.stopPropagation()}>
            <button className="modal-close" onClick={() => setEditingVideo(null)}>×</button>
            <h2>Изменить видео</h2>
            <form className="stack-form" onSubmit={saveVideo}>
              <input value={editTitle} onChange={(event) => setEditTitle(event.target.value)} maxLength={120} required />
              <textarea value={editDescription} onChange={(event) => setEditDescription(event.target.value)} rows={4} maxLength={5000} placeholder="Описание" />
              <label className="field-label">Видимость
                <select value={editVisibility} onChange={(event) => setEditVisibility(event.target.value as Video["visibility"])}>
                  <option value="public">Открытый доступ</option>
                  <option value="unlisted">Доступ по ссылке</option>
                  <option value="private">Приватное</option>
                </select>
              </label>
              <button className="primary-button" disabled={busy}>{busy ? "Сохранение..." : "Сохранить изменения"}</button>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}

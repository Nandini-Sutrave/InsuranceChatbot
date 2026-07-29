import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

let accessTokenInMemory = "";
let refreshPromise: Promise<string | null> | null = null;

export function setAccessToken(token: string) {
  accessTokenInMemory = token;
  if (typeof window !== "undefined") {
    if (token) sessionStorage.setItem("access_token", token);
    else sessionStorage.removeItem("access_token");
  }
}

export function getAccessToken() {
  if (!accessTokenInMemory && typeof window !== "undefined") {
    accessTokenInMemory = sessionStorage.getItem("access_token") || "";
  }
  return accessTokenInMemory;
}

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

async function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = apiClient
      .post("/api/v1/auth/refresh")
      .then((res) => {
        const token = res.data.access_token as string;
        setAccessToken(token);
        return token;
      })
      .catch(() => {
        setAccessToken("");
        return null;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined;
    const path = original?.url || "";
    if (error.response?.status === 401 && original && !original._retry && !path.includes("/auth/login") && !path.includes("/auth/refresh")) {
      original._retry = true;
      const token = await refreshAccessToken();
      if (token) {
        original.headers.Authorization = `Bearer ${token}`;
        return apiClient(original);
      }
      if (typeof window !== "undefined") window.location.href = "/login?session_expired=true";
    }
    const detail = (error.response?.data as { detail?: string })?.detail;
    return Promise.reject(new Error(detail || error.message || "Request failed"));
  }
);

export type Role = { id: string; name: string; description?: string };
export type User = { id: string; email: string; full_name: string; is_active: boolean; roles: Role[] };
export type KnowledgeBase = { id: string; name: string; description?: string };
export type DocumentItem = { id: string; filename: string; file_size: number; mime_type: string; status: string; error_message?: string; product_id: string; created_at: string };
export type Source = { document_id?: string; filename: string; page_number?: string | number; chunk_text?: string; section_title?: string; clause_type?: string; relevance_rank?: number; relevance_score?: number };
export type ChatMessage = { id: string; role: "user" | "assistant"; content: string; sources?: Source[]; created_at: string; feedback?: { id: string; rating: string; comment?: string } };
export type ChatSession = { id: string; title: string; created_at: string };

export const api = {
  login: async (email: string, password: string) => (await apiClient.post("/api/v1/auth/login", { email, password })).data,
  register: async (payload: { email: string; password: string; full_name: string }) => (await apiClient.post("/api/v1/auth/register", payload)).data,
  me: async () => (await apiClient.get<User>("/api/v1/users/me")).data,
  logout: async () => (await apiClient.post("/api/v1/auth/logout")).data,
  refresh: async () => (await apiClient.post("/api/v1/auth/refresh")).data,
  getOAuthUrl: async (provider: "google" | "microsoft", redirectUri: string, state: string) =>
    (await apiClient.get(`/api/v1/auth/oauth/${provider}/login`, { params: { redirect_uri: redirectUri, state } })).data as { redirect_url: string },
  exchangeOAuthCode: async (provider: string, code: string, state: string) =>
    (await apiClient.post(`/api/v1/auth/oauth/${provider}/callback`, { code, state })).data,
  listKnowledgeBases: async () => (await apiClient.get<KnowledgeBase[]>("/api/v1/documents/kb")).data,
  createKnowledgeBase: async (payload: { name: string; description?: string }) => (await apiClient.post("/api/v1/documents/kb", payload)).data,
  listDocuments: async () => (await apiClient.get<DocumentItem[]>("/api/v1/documents/")).data,
  uploadDocument: async (productId: string, file: File, onUploadProgress?: (progress: number) => void) => {
    const formData = new FormData();
    formData.append("product_id", productId);
    formData.append("file", file);
    const response = await apiClient.post("/api/v1/documents/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (event) => {
        if (event.total && onUploadProgress) onUploadProgress(Math.round((event.loaded / event.total) * 100));
      },
    });
    return response.data;
  },
  deleteDocument: async (documentId: string) => (await apiClient.delete(`/api/v1/documents/${documentId}`)).data,
  listChatSessions: async () => (await apiClient.get<ChatSession[]>("/api/v1/chat/history")).data,
  getChatSession: async (id: string) => (await apiClient.get<{ messages: ChatMessage[] }>(`/api/v1/chat/history/${id}`)).data,
  sendMessage: async (payload: { content: string; conversation_id?: string; product_id?: string }) => (await apiClient.post<ChatMessage>("/api/v1/chat/message", payload)).data,
  submitFeedback: async (payload: { message_id: string; rating: "thumbs_up" | "thumbs_down"; comment?: string }) => (await apiClient.post("/api/v1/chat/feedback", payload)).data,
};

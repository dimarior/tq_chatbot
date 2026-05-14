import type { Role } from "./messages";

export type Source = {
  url: string;
  title: string | null;
  score: number;
};

export type ApiMessageRow = {
  id: string;
  parent_id: string | null;
  role: Role;
  content: string;
  sources: Source[] | null;
  created_at: string;
};

export type ApiThread = {
  id: string;
  title: string;
  archived: boolean;
};

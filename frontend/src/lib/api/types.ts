export interface PageMeta {
  next_cursor: string | null;
  prev_cursor: string | null;
  has_more: boolean;
  has_prev: boolean;
}

export interface ApiResponse<T> {
  data: T;
  meta: PageMeta;
}

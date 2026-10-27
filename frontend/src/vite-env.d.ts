/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 后端 API 基地址；留空表示同源（由后端托管页面） */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

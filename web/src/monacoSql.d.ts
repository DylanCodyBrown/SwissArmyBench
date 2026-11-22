// Monaco's SQL grammar module (lazy/codeEditor.ts reads its words to colour JOIN like the other keywords).
declare module "monaco-editor/languages/definitions/sql/sql.js" {
  import type { languages } from "monaco-editor";
  export const language: languages.IMonarchLanguage;
  export const conf: languages.LanguageConfiguration;
}

// Language of the Synapse content (alerts, answers, copilot). UI labels stay in English.
import { createContext, useContext } from "react";

export const LANGS = [
  { id: "en", label: "EN" }, { id: "fr", label: "FR" }, { id: "ar", label: "عربي" },
];
export const LangContext = createContext({ lang: "en", setLang: () => {} });
export const useLang = () => useContext(LangContext);
export const dirOf = (lang) => (lang === "ar" ? "rtl" : "ltr");

// The best text for a notification in a language: Claude's persona rewrite, else built-in translation.
export const noteText = (n, lang) => n.texts_llm?.[lang] || n.texts?.[lang] || n.text;

export const T = {
  copilot: { en: "Operator copilot", fr: "Copilote opérateur", ar: "مساعد المشغّل" },
  suggestions: { en: "Suggested actions", fr: "Actions suggérées", ar: "إجراءات مقترحة" },
  approve: { en: "Approve", fr: "Approuver", ar: "موافقة" },
  dismiss: { en: "Dismiss", fr: "Ignorer", ar: "تجاهل" },
  report: { en: "Draft incident report", fr: "Rédiger un rapport", ar: "صياغة تقرير" },
  approved: { en: "approved · recorded, not applied", fr: "approuvé · enregistré, non appliqué", ar: "تمت الموافقة · سُجّل ولم يُطبّق" },
  dismissed: { en: "dismissed", fr: "ignoré", ar: "تم التجاهل" },
  refresh: { en: "Refresh", fr: "Actualiser", ar: "تحديث" },
};
export const t = (key, lang) => T[key]?.[lang] || T[key]?.en || key;

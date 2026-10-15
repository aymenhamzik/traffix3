"""
Built-in translations (English, French, Arabic) used when no language model is available,
and as the reference every model rewrite is checked against.
"""
LANGS = ["en", "fr", "ar"]
LANG_NAMES = {"en": "English", "fr": "French", "ar": "Arabic (Modern Standard Arabic)"}

ALERTS = {
    "INCIDENT": {"en": "Lane blocked on {edge} (confidence {confidence:.0%}). Cause not determined.",
                 "fr": "Voie bloquée sur {edge} (confiance {confidence:.0%}). Cause non déterminée.",
                 "ar": "مسار مغلق على {edge} (درجة الثقة {confidence:.0%}). السبب غير محدد."},
    "FLOOD": {"en": "Flood alert: {edge} is impassable.",
              "fr": "Alerte inondation : {edge} est impraticable.",
              "ar": "تنبيه فيضان: الطريق {edge} غير صالح للمرور."},
    "RAIN": {"en": "Rain: expect traffic about {slow:.0%} slower. Signal timings lengthened.",
             "fr": "Pluie : circulation environ {slow:.0%} plus lente. Durées des feux allongées.",
             "ar": "أمطار: توقّعوا حركة مرور أبطأ بنحو {slow:.0%}. تم تمديد توقيت الإشارات."},
    "ROUTE_B": {"en": "Route B around {edge} saves about {saving_s} s.",
                "fr": "Un itinéraire bis autour de {edge} fait gagner environ {saving_s} s.",
                "ar": "مسار بديل حول {edge} يوفّر نحو {saving_s} ثانية."},
    "CONGESTION": {"en": "Heavy traffic on {edge}: {stopped_vehicles} vehicles stopped near {junction}.",
                   "fr": "Circulation dense sur {edge} : {stopped_vehicles} véhicules à l'arrêt près de {junction}.",
                   "ar": "ازدحام شديد على {edge}: {stopped_vehicles} مركبة متوقفة قرب {junction}."},
    "PEAK_FORECAST": {"en": "Busy period expected around {when} ({direction} traffic). Allow extra time.",
                      "fr": "Période chargée prévue vers {when} (circulation {direction}). Prévoyez du temps.",
                      "ar": "فترة ازدحام متوقعة حوالي {when} ({direction}). خصّصوا وقتًا إضافيًا."},
    "AMBULANCE_NEAR": {"en": "{kind} reaching {tls} in about {eta_s:.0f} s: keep the junction clear.",
                       "fr": "{kind} arrive à {tls} dans environ {eta_s:.0f} s : dégagez le carrefour.",
                       "ar": "{kind} يصل إلى {tls} خلال حوالي {eta_s:.0f} ثانية: أبقوا التقاطع خاليًا."},
    "TRANSIT_LATE": {"en": "{vehicle} on line {line} is late (gap {gap:.0f} s).",
                     "fr": "{vehicle} de la ligne {line} est en retard (écart {gap:.0f} s).",
                     "ar": "{vehicle} على الخط {line} متأخر (الفارق {gap:.0f} ثانية)."},
    "DATA_STALE": {"en": "Detector {lane} stopped updating; junction on local control.",
                   "fr": "Le détecteur {lane} ne transmet plus ; carrefour en contrôle local.",
                   "ar": "الكاشف {lane} توقف عن الإرسال؛ التقاطع يعمل بالتحكم المحلي."},
    "EMERGENCY_GRANTED": {"en": "Green given to {vehicle} at {tls}.",
                          "fr": "Feu vert donné à {vehicle} à {tls}.",
                          "ar": "تم منح الضوء الأخضر لـ {vehicle} عند {tls}."},
    "EMERGENCY_DENIED": {"en": "Priority denied to {vehicle} at {tls}: exit lane full.",
                         "fr": "Priorité refusée à {vehicle} à {tls} : voie de sortie saturée.",
                         "ar": "رُفضت الأولوية لـ {vehicle} عند {tls}: طريق الخروج ممتلئ."},
    "EMERGENCY_PREPARE": {"en": "{tls} is preparing for {vehicle} (arrival in {eta_s:.0f} s).",
                          "fr": "{tls} se prépare pour {vehicle} (arrivée dans {eta_s:.0f} s).",
                          "ar": "{tls} يستعد لـ {vehicle} (الوصول خلال {eta_s:.0f} ثانية)."},
    "WALK_GRANTED": {"en": "Walk signal given at {tls} after a long wait.",
                     "fr": "Feu piéton vert à {tls} après une longue attente.",
                     "ar": "إشارة عبور المشاة خضراء عند {tls} بعد انتظار طويل."},
    "CLEARANCE": {"en": "Green held at {tls} until the crossing was clear.",
                  "fr": "Feu vert retenu à {tls} jusqu'à ce que le passage piéton soit dégagé.",
                  "ar": "تم تأجيل الضوء الأخضر عند {tls} حتى خلوّ ممر المشاة."},
    "TRANSIT_GRANTED": {"en": "Priority given to late bus {vehicle} at {tls}.",
                        "fr": "Priorité donnée au bus en retard {vehicle} à {tls}.",
                        "ar": "مُنحت الأولوية للحافلة المتأخرة {vehicle} عند {tls}."},
}

WORDS = {   # values substituted inside templates
    "inbound": {"en": "inbound", "fr": "vers le centre", "ar": "باتجاه الوسط"},
    "outbound": {"en": "outbound", "fr": "sortant du centre", "ar": "خارج الوسط"},
    "two-way": {"en": "two-way", "fr": "dans les deux sens", "ar": "في الاتجاهين"},
    "ambulance": {"en": "Ambulance", "fr": "Ambulance", "ar": "سيارة إسعاف"},
    "fire truck": {"en": "Fire truck", "fr": "Camion de pompiers", "ar": "شاحنة إطفاء"},
    "police car": {"en": "Police car", "fr": "Voiture de police", "ar": "سيارة شرطة"},
}


def alert_text(event_type, lang, fields):
    tpl = ALERTS.get(event_type, {}).get(lang)
    if not tpl:
        return None
    f = dict(fields)
    for k in ("direction", "kind"):
        if isinstance(f.get(k), str) and f[k].lower() in WORDS:
            f[k] = WORDS[f[k].lower()][lang]
    try:
        return tpl.format(**f)
    except (KeyError, ValueError, IndexError):
        return None


COPILOT = {
    "summary": {
        "en": "{vehicles} vehicles and {people} pedestrians in the network. {incidents} incident(s), "
              "{jams} congested road(s), {stale} stale detector(s), {emergency} emergency vehicle(s) active. {weather}",
        "fr": "{vehicles} véhicules et {people} piétons sur le réseau. {incidents} incident(s), "
              "{jams} route(s) congestionnée(s), {stale} détecteur(s) hors service, {emergency} véhicule(s) d'urgence actif(s). {weather}",
        "ar": "{vehicles} مركبة و{people} من المشاة في الشبكة. حوادث: {incidents}، طرق مزدحمة: {jams}، "
              "كواشف متوقفة: {stale}، مركبات طوارئ نشطة: {emergency}. {weather}"},
    "dry": {"en": "Weather: dry.", "fr": "Météo : sec.", "ar": "الطقس: جاف."},
    "rain": {"en": "Rain: {rain:.0%} intensity.", "fr": "Pluie : intensité {rain:.0%}.", "ar": "أمطار: شدة {rain:.0%}."},
    "s_stale": {"en": "Check detector {lane}: its junction is on backup control.",
                "fr": "Vérifier le détecteur {lane} : son carrefour est en mode secours.",
                "ar": "تحقّقوا من الكاشف {lane}: التقاطع يعمل في وضع الطوارئ."},
    "s_incident": {"en": "Send a patrol to {edge} (blocked lane, confidence {confidence:.0%}) and inform drivers.",
                   "fr": "Envoyer une patrouille sur {edge} (voie bloquée, confiance {confidence:.0%}) et informer les conducteurs.",
                   "ar": "أرسلوا دورية إلى {edge} (مسار مغلق، الثقة {confidence:.0%}) وأبلغوا السائقين."},
    "s_jam": {"en": "Heavy traffic on {n} roads, worst on {edge}: consider a driver alert.",
              "fr": "Circulation dense sur {n} routes, surtout {edge} : envisager une alerte conducteurs.",
              "ar": "ازدحام على {n} طرق، أشدّه على {edge}: فكّروا في تنبيه السائقين."},
    "s_denied": {"en": "An emergency vehicle was refused at {tls} because the exit was full: clear the road ahead.",
                 "fr": "Un véhicule d'urgence a été refusé à {tls} (sortie saturée) : dégager la route en aval.",
                 "ar": "رُفضت مركبة طوارئ عند {tls} لأن طريق الخروج ممتلئ: أخلوا الطريق أمامها."},
    "s_rain": {"en": "Rain timings are active on every junction: review whether they are still needed.",
               "fr": "Les durées « pluie » sont actives partout : vérifier si elles restent nécessaires.",
               "ar": "توقيتات المطر مفعّلة في كل التقاطعات: راجعوا ما إذا كانت لا تزال ضرورية."},
    "s_none": {"en": "No action needed right now.", "fr": "Aucune action nécessaire pour l'instant.",
               "ar": "لا حاجة لأي إجراء حاليًا."},
    "report_title": {"en": "Incident report", "fr": "Rapport d'incident", "ar": "تقرير الحادث"},
    "report_events": {"en": "Key events (from the decision log):", "fr": "Événements clés (journal des décisions) :",
                      "ar": "الأحداث الرئيسية (من سجل القرارات):"},
    "english_note": {"en": "", "fr": "(détails en anglais sans clé API)", "ar": "(التفاصيل بالإنجليزية بدون مفتاح API)"},
}

EXPLAIN = {
    "found": {"en": "I found {n} decisions{about}:", "fr": "J'ai trouvé {n} décisions{about} :",
              "ar": "وجدتُ {n} قرارًا{about}:"},
    "about": {"en": " about {who}", "fr": " concernant {who}", "ar": " بخصوص {who}"},
    "note": {"en": "", "fr": "Sans clé API, les phrases restent en anglais.",
             "ar": "بدون مفتاح API تبقى الجمل بالإنجليزية."},
}


def phrase(table, key, lang, **fields):
    tpl = table[key].get(lang) or table[key]["en"]
    try:
        return tpl.format(**fields)
    except (KeyError, ValueError):
        return table[key]["en"].format(**fields)

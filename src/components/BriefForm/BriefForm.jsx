import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';

const PRICE_LABEL = { unset: 'Not stated', free: 'Free', paid: 'Paid' };

// Static mirror of GET /api/brief/fields (server.py, sourced from
// brief_fields.py). The hosted preview (Netlify) has no backend — server.py
// binds to localhost only, by design (CLAUDE.md: LOCAL_ONLY) — so that fetch
// always fails there. Before this, a failed fetch left a dev-facing error
// ("is server.py running?") in place of the form, which made the one public
// link to this project (linked from the case study) look broken on load
// instead of showing what it actually does. Used ONLY as a fallback when the
// live fetch fails; the real server's response always wins when reachable.
// Keep in sync with brief_fields.FIELDS by hand — nothing enforces this copy.
const FALLBACK_SPEC = {
    fields: [
        { name: 'event_type', kind: 'enum', required: true, label_en: 'Event type', label_ko: '행사 유형' },
        { name: 'person', kind: 'text', required: false, label_en: 'Speaker', label_ko: '연사' },
        { name: 'date', kind: 'date', required: true, label_en: 'Date', label_ko: '날짜' },
        { name: 'time', kind: 'time', required: false, label_en: 'Time', label_ko: '시간' },
        { name: 'timezone', kind: 'tz', required: false, label_en: 'Time zone', label_ko: '시간대' },
        { name: 'location', kind: 'text', required: true, label_en: 'Location', label_ko: '장소' },
        { name: 'map_url', kind: 'url', required: false, label_en: 'Map', label_ko: '지도' },
        { name: 'price_kind', kind: 'enum', required: false, label_en: 'Price', label_ko: '참가비' },
        { name: 'price', kind: 'money', required: false, label_en: 'Amount', label_ko: '금액' },
        { name: 'currency', kind: 'enum', required: false, label_en: 'Currency', label_ko: '통화' },
        { name: 'link', kind: 'url', required: false, label_en: 'Link', label_ko: '링크' },
        { name: 'topics', kind: 'list', required: false, label_en: 'Agenda', label_ko: '주제' },
    ],
    event_types: [
        { key: 'seminar', en: 'Seminar', ko: '세미나' },
        { key: 'webinar', en: 'Webinar', ko: '웨비나' },
        { key: 'conference', en: 'Conference', ko: '컨퍼런스' },
    ],
    timezones: ['PST', 'PDT', 'EST', 'EDT', 'KST', 'UTC', 'GMT', 'CET', 'JST'],
    currencies: ['KRW', 'USD', 'EUR', 'JPY'],
    price_kinds: ['unset', 'free', 'paid'],
};

/**
 * The typed brief form.
 *
 * Rendered FROM /api/brief/fields rather than hand-built here, so a field added
 * to brief_fields.FIELDS cannot silently fail to appear, and the enum this offers
 * is the enum the server validates against. Two copies of a field list drift;
 * one does not.
 *
 * Server-side errors are shown per field. The form does not re-implement the
 * validation to show them sooner — that would be the same rule in two places,
 * and the two would disagree.
 */
export function BriefForm({ values, onChange, errors = {}, disabled }) {
    const [spec, setSpec] = useState(null);

    useEffect(() => {
        fetch('/api/brief/fields')
            .then((res) => (res.ok ? res.json() : Promise.reject(new Error('unavailable'))))
            .then(setSpec)
            // No live server (e.g. the hosted preview) — fall back so the form
            // still renders and is explorable rather than showing an error.
            .catch(() => setSpec(FALLBACK_SPEC));
    }, []);

    if (!spec) return <p className="form-hint">Loading fields…</p>;

    const ko = Boolean(values.ko);
    const set = (name) => (e) => onChange({ ...values, [name]: e.target.value });
    const labelFor = (f) => (ko ? f.label_ko : f.label_en);

    // price and currency are only meaningful once the event is paid, and the
    // server rejects an amount without a kind — so hide rather than offer them.
    // map_url is never shown: it reads as an empty, unexplained field ("Google
    // Maps what?") when what it actually does is get filled in automatically
    // from Location, silently, server-side. A manual override is one field the
    // form does not need to expose to do that.
    const hidden = (name) =>
        name === 'map_url' ||
        ((name === 'price' || name === 'currency') && values.price_kind !== 'paid');

    const field = (f) => {
        if (hidden(f.name)) return null;
        const err = errors[f.name];
        const id = `brief-${f.name}`;
        let control;

        if (f.name === 'event_type') {
            control = (
                <select id={id} value={values.event_type || ''} onChange={set('event_type')} disabled={disabled}>
                    <option value="">—</option>
                    {spec.event_types.map((t) => (
                        <option key={t.key} value={ko ? t.ko : t.en}>{ko ? t.ko : t.en}</option>
                    ))}
                </select>
            );
        } else if (f.name === 'price_kind') {
            control = (
                <select id={id} value={values.price_kind || 'unset'} onChange={set('price_kind')} disabled={disabled}>
                    {spec.price_kinds.map((k) => <option key={k} value={k}>{PRICE_LABEL[k] || k}</option>)}
                </select>
            );
        } else if (f.name === 'currency') {
            control = (
                <select id={id} value={values.currency || 'KRW'} onChange={set('currency')} disabled={disabled}>
                    {spec.currencies.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
            );
        } else if (f.kind === 'tz') {
            control = (
                <select id={id} value={values.timezone || ''} onChange={set('timezone')} disabled={disabled}>
                    <option value="">—</option>
                    {spec.timezones.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
            );
        } else if (f.kind === 'list') {
            // One agenda item per line. The server splits and trims; this does not
            // parse, so a stray comma cannot become two topics.
            control = (
                <textarea
                    id={id} rows={3} disabled={disabled}
                    className="content-input"
                    placeholder={ko ? '한 줄에 하나씩' : 'One per line'}
                    value={values.topics_text ?? (values.topics || []).join('\n')}
                    onChange={(e) => onChange({
                        ...values,
                        // The raw text is kept as typed. Re-deriving the box from the
                        // parsed list trimmed every keystroke, so a space or a new line
                        // vanished the moment it was typed and the whole agenda
                        // collapsed into one topic. Only the parsed list is sent.
                        topics_text: e.target.value,
                        topics: e.target.value.split('\n').map((s) => s.trim()).filter(Boolean),
                    })}
                />
            );
        } else {
            const type = f.kind === 'date' ? 'date'
                : f.kind === 'time' ? 'time'
                : f.kind === 'money' ? 'number' : 'text';
            control = (
                <input
                    id={id} type={type} disabled={disabled}
                    value={values[f.name] ?? ''}
                    onChange={set(f.name)}
                />
            );
        }

        return (
            <div className="form-group" key={f.name}>
                <label htmlFor={id}>
                    {labelFor(f)}{f.required && <span className="required"> *</span>}
                </label>
                {control}
                {err && <span className="field-error">{err}</span>}
            </div>
        );
    };

    return (
        <div className="brief-form">
            <div className="form-group">
                <label className="inline-check">
                    <input
                        id="brief-ko" type="checkbox" checked={ko} disabled={disabled}
                        onChange={(e) => onChange({ ...values, ko: e.target.checked })}
                    />
                    {' '}Korean output (한국어)
                </label>
            </div>
            {spec.fields.map(field)}
        </div>
    );
}

BriefForm.propTypes = {
    values: PropTypes.object.isRequired,
    onChange: PropTypes.func.isRequired,
    errors: PropTypes.object,
    disabled: PropTypes.bool,
};

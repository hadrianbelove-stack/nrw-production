/**
 * NRW Shared Config — single source of truth for service maps and utilities
 * Used by both assets/app.js (desktop) and mobile/mobile.js
 */
const NRWConfig = {
    // Streaming service definitions (colors in CSS :root variables)
    SERVICE_MAP: {
        netflix:   { class: 'netflix',   name: 'NETFLIX',    badgeName: 'NETFLIX',   btnName: 'Netflix',    matches: ['netflix'],         logo: 'netflix%20square%20logo.png', wideLogo: 'services/netflix_wide.png' },
        max:       { class: 'max',       name: 'MAX',        badgeName: 'MAX',       btnName: 'Max',        matches: ['max', 'hbo'],      logo: 'max%20logo.jpeg', wideLogo: 'services/max_wide.png' },
        disney:    { class: 'disney',    name: 'DISNEY+',    badgeName: 'DISNEY+',   btnName: 'Disney+',    matches: ['disney'],           logo: 'disney%20plus%20logo%20sqaure.jpg', wideLogo: 'services/disney_plus_wide.png' },
        prime:     { class: 'prime',     name: 'PRIME VIDEO', badgeName: 'PRIME',    btnName: 'Prime',      matches: ['amazon', 'prime'],  logo: 'primevideo.png', wideLogo: 'services/prime_video_wide.png' },
        hulu:      { class: 'hulu',      name: 'HULU',       badgeName: 'HULU',      btnName: 'Hulu',       matches: ['hulu'],             logo: 'hulu%20sqaure%20logo.png', wideLogo: 'services/hulu_wide.png' },
        peacock:   { class: 'peacock',   name: 'PEACOCK',    badgeName: 'PEACOCK',   btnName: 'Peacock',    matches: ['peacock'],           logo: 'peaccok%20logo.png', wideLogo: 'services/peacock_wide.png' },
        mubi:      { class: 'mubi',      name: 'MUBI',       badgeName: 'MUBI',      btnName: 'MUBI',       matches: ['mubi'],             logo: 'mubi%20logo.png', wideLogo: 'services/mubi_wide.png' },
        shudder:   { class: 'shudder',   name: 'SHUDDER',    badgeName: 'SHUDDER',   btnName: 'Shudder',    matches: ['shudder'],           logo: 'shudder%20logo.jpg' },
        criterion: { class: 'criterion', name: 'CRITERION',  badgeName: 'CRITERION', btnName: 'Criterion',  matches: ['criterion'],         logo: 'criterion%20logo%20sqaure.png', wideLogo: 'services/criterion_wide.png' },
        tubi:      { class: 'tubi',      name: 'TUBI',       badgeName: 'TUBI',      btnName: 'Tubi',       matches: ['tubi'],             logo: 'tubi.png' },
        amc:       { class: 'amc',       name: 'AMC+',       badgeName: 'AMC+',      btnName: 'AMC+',       matches: ['amc'],              logo: 'amc-plus-logo-png_seeklogo-483819.png', wideLogo: 'services/amc_plus_wide.png' },
        youtube:   { class: 'youtube',   name: 'YOUTUBE',    badgeName: 'YOUTUBE',   btnName: 'YouTube',    matches: ['youtube'] },
        paramount: { class: 'paramount', name: 'PARAMOUNT+', badgeName: 'P+',        btnName: 'Paramount+', matches: ['paramount'],         logo: 'paramoung%20plus%20logo.png', wideLogo: 'services/paramount_plus_wide.png' },
        kanopy:    { class: 'kanopy',    name: 'KANOPY',     badgeName: 'KANOPY',    btnName: 'Kanopy',     matches: ['kanopy'],            logo: 'kanopy.png' },
        hoopla:    { class: 'hoopla',    name: 'HOOPLA',     badgeName: 'HOOPLA',    btnName: 'Hoopla',     matches: ['hoopla'],            logo: 'hoopla.png' },
        roku:      { class: 'roku',      name: 'ROKU CH.',   badgeName: 'ROKU',      btnName: 'Roku Ch.',   matches: ['roku'],              logo: 'roku.png' },
        pluto:     { class: 'pluto',     name: 'PLUTO TV',   badgeName: 'PLUTO',     btnName: 'Pluto TV',   matches: ['pluto'],             logo: 'Pluto_TV_2020_logo.png' },
        crackle:   { class: 'crackle',   name: 'CRACKLE',    badgeName: 'CRACKLE',   btnName: 'Crackle',    matches: ['crackle'],           logo: 'Crackle-Symbol.png' },
        fawesome:  { class: 'fawesome',  name: 'FAWESOME',   badgeName: 'FAWESOME',  btnName: 'Fawesome',   matches: ['fawesome'],          logo: 'fawesome.png' },
        fandango:      { class: 'fandango',      name: 'FANDANGO',   badgeName: 'FANDANGO',  btnName: 'Fandango',      matches: ['fandango'],          logo: 'fandangoathome.png', wideLogo: 'services/fandango_wide.png' },
        docuramafilms: { class: 'docuramafilms', name: 'DOCURAMA',   badgeName: 'DOCURAMA',  btnName: 'Docurama',      matches: ['docurama'],          wideLogo: 'services/docuramafilms_wide.png' },
        fandor:        { class: 'fandor',        name: 'FANDOR',     badgeName: 'FANDOR',    btnName: 'Fandor',        matches: ['fandor'],            wideLogo: 'services/fandor_wide.png' },
        bloodstream:   { class: 'other',         name: 'BLOODSTREAM', badgeName: 'BLOODSTREAM', btnName: 'Bloodstream', matches: ['bloodstream'] },
        angel:         { class: 'other',         name: 'ANGEL STUDIOS', badgeName: 'ANGEL STUDIOS', btnName: 'Angel Studios', matches: ['angel studios'] },
    },

    // VOD (rent/buy) service definitions (colors in CSS :root variables)
    VOD_SERVICE_MAP: {
        amazon:    { key: 'amazon',    matches: ['amazon', 'prime'], label: 'AMAZON',     btnLabel: 'Rent Amazon',   logo: 'pngimg.com%20-%20amazon_PNG17.png', wideLogo: 'services/amazon_wide.png' },
        apple:     { key: 'apple',     matches: ['apple', 'itunes'], label: 'APPLE TV',  btnLabel: 'Rent Apple TV', logo: 'apple%20logo.png', wideLogo: 'services/apple_tv_wide.png' },
        fandango:  { key: 'fandango',  matches: ['fandango'],        label: 'FANDANGO',  btnLabel: 'Rent Fandango', logo: 'fandangoathome.png', wideLogo: 'services/fandango_wide.png' },
        youtube:   { key: 'youtube',   matches: ['youtube'],         label: 'YOUTUBE',   btnLabel: 'Rent YouTube',  logo: null },
        screening: { key: 'screening', matches: ['eventive'],        label: 'BUY TICKET', btnLabel: 'Buy Ticket',  logo: null,
                     linkMatches: ['eventive.org', 'festivalplayer', 'shift72.com'] },
        plex:      { key: 'plex',      matches: ['plex'],            label: 'PLEX',       btnLabel: 'Watch on Plex', logo: null, wideLogo: 'services/plex_wide.png', fallback: true },
    },

    // Date strips adopt the active filter's color when exactly one filter is on
    STRIP_COLORS: {
        'indie': '#00d4aa',
        'horror': '#ff5e57',
        'action': '#ff9500',
        'comedy': '#ffd32a',
        'family': '#2ed573',
        'thriller': '#d63031',
        'foreign': '#e84393',
        'documentary': '#4A90D9',
        'restorations': '#C8A951'
    },

    // Country abbreviations — 3-letter Olympic codes (except UK stays UK)
    countryAbbrev: {
        // USA & UK kept as recognizable exceptions; everything else 3-letter (IOC-style).
        // Each country maps from BOTH its full name AND its 2-letter ISO code.
        'united states of america': 'USA', 'united states': 'USA', 'usa': 'USA', 'us': 'USA',
        'united kingdom': 'UK', 'great britain': 'UK', 'gb': 'UK', 'uk': 'UK',
        'india': 'IND', 'in': 'IND',
        'canada': 'CAN', 'ca': 'CAN',
        'france': 'FRA', 'fr': 'FRA',
        'mexico': 'MEX', 'mx': 'MEX',
        'australia': 'AUS', 'au': 'AUS',
        'germany': 'GER', 'de': 'GER',
        'italy': 'ITA', 'it': 'ITA',
        'japan': 'JPN', 'jp': 'JPN',
        'south korea': 'KOR', 'kr': 'KOR',
        'belgium': 'BEL', 'be': 'BEL',
        'spain': 'ESP', 'es': 'ESP',
        'indonesia': 'IDN', 'id': 'IDN',
        'brazil': 'BRA', 'br': 'BRA',
        'argentina': 'ARG', 'ar': 'ARG',
        'thailand': 'THA', 'th': 'THA',
        'new zealand': 'NZL', 'nz': 'NZL',
        'austria': 'AUT', 'at': 'AUT',
        'poland': 'POL', 'pl': 'POL',
        'china': 'CHN', 'cn': 'CHN',
        'taiwan': 'TWN', 'tw': 'TWN',
        'denmark': 'DEN', 'dk': 'DEN',
        'netherlands': 'NED', 'nl': 'NED',
        'ireland': 'IRL', 'ie': 'IRL',
        'turkey': 'TUR', 'tr': 'TUR',
        'nigeria': 'NGA', 'ng': 'NGA',
        'philippines': 'PHI', 'ph': 'PHI',
        'finland': 'FIN', 'fi': 'FIN',
        'colombia': 'COL', 'co': 'COL',
        'sweden': 'SWE', 'se': 'SWE',
        'russia': 'RUS', 'ru': 'RUS',
        'hong kong': 'HKG', 'hk': 'HKG',
        'ukraine': 'UKR', 'ua': 'UKR',
        'greece': 'GRE', 'gr': 'GRE',
        'israel': 'ISR', 'il': 'ISR',
        'georgia': 'GEO', 'ge': 'GEO',
        'saudi arabia': 'KSA', 'sa': 'KSA',
        'czech republic': 'CZE', 'cz': 'CZE',
        'cuba': 'CUB', 'cu': 'CUB',
        'switzerland': 'SUI', 'ch': 'SUI',
        'south africa': 'RSA', 'za': 'RSA',
        'venezuela': 'VEN', 've': 'VEN',
        'croatia': 'CRO', 'hr': 'CRO',
        'guatemala': 'GUA', 'gt': 'GUA',
        'kenya': 'KEN', 'ke': 'KEN',
        'iceland': 'ISL', 'is': 'ISL',
        'bulgaria': 'BUL', 'bg': 'BUL',
        'norway': 'NOR', 'no': 'NOR',
        'iraq': 'IRQ', 'iq': 'IRQ',
        'hungary': 'HUN', 'hu': 'HUN',
        'nepal': 'NEP', 'np': 'NEP',
        'slovenia': 'SLO', 'si': 'SLO',
        'cambodia': 'CAM', 'kh': 'CAM',
        'morocco': 'MAR', 'ma': 'MAR',
        'chile': 'CHL', 'cl': 'CHL',
        'singapore': 'SGP', 'sg': 'SGP',
        'armenia': 'ARM', 'am': 'ARM',
        'united arab emirates': 'UAE', 'ae': 'UAE',
        'palestinian territory': 'PLE', 'palestine': 'PLE', 'ps': 'PLE',
        'bosnia and herzegovina': 'BIH', 'ba': 'BIH',
        'unknown': '—',
    },

    abbreviateCountry(country) {
        if (!country) return null;
        const shortened = NRWConfig.countryAbbrev[country.toLowerCase()];
        if (shortened) return shortened;
        // Unmapped (rare/new country): fall back to first 3 letters, uppercased,
        // so the display stays 3-letter. Add it to the map above when it appears.
        return country.replace(/[^A-Za-z]/g, '').slice(0, 3).toUpperCase() || country;
    },

    // Lightbox variant: full country names, with USA as the one abbreviation exception.
    lightboxCountry(country) {
        if (!country) return null;
        const lower = country.toLowerCase();
        if (['united states of america', 'united states', 'us', 'usa'].includes(lower)) return 'USA';
        const isoToFull = {
            'ar':'Argentina','au':'Australia','at':'Austria','be':'Belgium','br':'Brazil',
            'bg':'Bulgaria','kh':'Cambodia','ca':'Canada','cl':'Chile','cn':'China',
            'co':'Colombia','hr':'Croatia','cu':'Cuba','cz':'Czech Republic','dk':'Denmark',
            'fi':'Finland','fr':'France','ge':'Georgia','de':'Germany','gr':'Greece',
            'gt':'Guatemala','hk':'Hong Kong','hu':'Hungary','in':'India','id':'Indonesia',
            'iq':'Iraq','ie':'Ireland','il':'Israel','it':'Italy','jp':'Japan','ke':'Kenya',
            'kr':'South Korea','ma':'Morocco','mx':'Mexico','np':'Nepal','nl':'Netherlands',
            'nz':'New Zealand','ng':'Nigeria','no':'Norway','ph':'Philippines','pl':'Poland',
            'pt':'Portugal','ro':'Romania','ru':'Russia','sa':'Saudi Arabia','sg':'Singapore',
            'si':'Slovenia','za':'South Africa','es':'Spain','se':'Sweden','ch':'Switzerland',
            'tw':'Taiwan','th':'Thailand','tr':'Turkey','ua':'Ukraine',
            'gb':'United Kingdom','uk':'United Kingdom','ve':'Venezuela',
        };
        return isoToFull[lower] || country;
    },

    // Strip storefront wrappers so we match the real brand, not the platform it's
    // sold through. "Shudder Amazon Channel" / "Britbox Apple TV Channel" /
    // "Starz Roku Premium Channel" are the brand (Shudder/Britbox/Starz) billed
    // through Amazon/Apple/Roku — the badge should name the brand. Leaves genuine
    // services alone ("Amazon Prime Video", "The Roku Channel").
    cleanServiceName(rawName) {
        if (!rawName) return rawName;
        const stripped = rawName.replace(/\s+(Amazon|Apple TV|Roku Premium)\s+Channel\s*$/i, '').trim();
        return stripped || rawName;
    },

    resolveService(rawName) {
        if (!rawName) return null;
        const s = NRWConfig.cleanServiceName(rawName).toLowerCase();
        for (const entry of Object.values(NRWConfig.SERVICE_MAP)) {
            if (entry.matches.some(m => s.includes(m))) return entry;
        }
        return null;
    },

    resolveVODService(serviceName, link) {
        if (!serviceName) return null;
        const s = serviceName.toLowerCase();
        for (const entry of Object.values(NRWConfig.VOD_SERVICE_MAP)) {
            if (entry.matches.some(m => s.includes(m))) return entry;
        }
        if (link) {
            for (const entry of Object.values(NRWConfig.VOD_SERVICE_MAP)) {
                if (entry.linkMatches && entry.linkMatches.some(m => link.includes(m))) return entry;
            }
        }
        return null;
    },

    // True if a movie carries a given genre/category tag. Genre views show
    // EVERY film with the tag — slop and fests included — so this is tag-only,
    // with no slop/fest gating.
    movieMatchesGenre(movie, filter) {
        switch (filter) {
            case 'indie':        return !!movie.filters?.is_indie;
            case 'foreign':      return !!(movie.filters?.is_foreign ??
                                     (movie.original_language && movie.original_language !== 'en'));
            case 'restorations': return !!movie.filters?.is_restoration;
            case 'documentary':  return !!movie.filters?.is_documentary;
            case 'horror':
            case 'action':
            case 'comedy':
            case 'family':
            case 'thriller':     return (movie.genres || []).some(g => g.toLowerCase().includes(filter));
            default:             return false;
        }
    },

    // Accent-insensitive substring search across the fields users actually type
    matchesSearch(movie, query) {
        const norm = s => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
        const nq = norm(query);
        return norm(movie.title || '').includes(nq) ||
               norm(movie.original_title || '').includes(nq) ||
               norm(movie.crew?.director || movie.director || '').includes(nq) ||
               norm((movie.crew?.cast || []).join(' ')).includes(nq) ||
               norm(movie.capsule || movie.synopsis || '').includes(nq) ||
               norm((movie.genres || []).join(' ')).includes(nq) ||
               norm(movie.country || '').includes(nq) ||
               String(movie.year || '').includes(query);
    },

    // Slop visibility: 'free' hides slop, 'only' shows only slop, 'all' lets everything through
    matchesSlopMode(movie, mode) {
        if (mode === 'free') return !movie.is_slop;
        if (mode === 'only') return !!movie.is_slop;
        return true;
    },

    // Staff pick ("Selects"): pipeline flag, featured, or the staff-picks list.
    // IDs are mixed int/string in data.json — always compare as strings.
    isStaffPick(movie, staffPicks) {
        return !!(movie.filters?.is_staff_pick || movie.featured ||
                  (staffPicks || []).some(id => String(id) === String(movie.id)));
    },

    // Render a tiny markdown subset (**bold**, *italic*) to safe HTML.
    // HTML is escaped first so synopsis text can never inject markup.
    // Canonical spec: docs/STYLE_GUIDE.md "Synopsis / Capsule Text Formatting".
    renderMarkdown(text) {
        const esc = (text || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        return esc
            .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
            .replace(/\*([^*]+)\*/g, '<em>$1</em>')
            .replace(/\[([^\]]+)\]\((https:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
            // Paragraph breaks: collapse any run of newlines to ONE <br> — a tight
            // line break, not a full blank-line gap. Capsule text stores breaks as \n.
            .replace(/\n+/g, '<br>');
    }
};

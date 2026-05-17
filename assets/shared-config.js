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

    // Country abbreviations — 3-letter Olympic codes (except UK stays UK)
    countryAbbrev: {
        'united states of america': 'USA', 'united states': 'USA', 'usa': 'USA', 'us': 'USA',
        'united kingdom': 'UK', 'great britain': 'UK', 'gb': 'UK',
        'india': 'IND', 'in': 'IND',
        'canada': 'CAN',
        'france': 'FRA', 'fr': 'FRA',
        'mexico': 'MEX', 'mx': 'MEX',
        'australia': 'AUS',
        'germany': 'GER',
        'italy': 'ITA', 'it': 'ITA',
        'japan': 'JPN', 'jp': 'JPN',
        'south korea': 'KOR', 'kr': 'KOR',
        'belgium': 'BEL',
        'spain': 'ESP', 'es': 'ESP',
        'indonesia': 'INA', 'id': 'INA',
        'brazil': 'BRA',
        'argentina': 'ARG',
        'thailand': 'THA', 'th': 'THA',
        'new zealand': 'NZL',
        'austria': 'AUT',
        'poland': 'POL', 'pl': 'POL',
        'china': 'CHN',
        'taiwan': 'TPE', 'tw': 'TPE',
        'denmark': 'DEN', 'dk': 'DEN',
        'netherlands': 'NED',
        'ireland': 'IRL',
        'turkey': 'TUR', 'tr': 'TUR',
        'nigeria': 'NGR',
        'philippines': 'PHI',
        'finland': 'FIN',
        'colombia': 'COL',
        'sweden': 'SWE',
        'russia': 'RUS',
        'hong kong': 'HKG',
        'ukraine': 'UKR',
        'singapore': 'SGP',
        'armenia': 'ARM',
        'greece': 'GRE',
        'palestinian territory': 'PLE',
        'israel': 'ISR',
        'georgia': 'GEO',
        'united arab emirates': 'UAE',
        'saudi arabia': 'KSA',
        'czech republic': 'CZE',
        'cuba': 'CUB',
        'switzerland': 'SUI',
        'south africa': 'RSA',
        'venezuela': 'VEN',
        'croatia': 'CRO',
        'guatemala': 'GUA',
        'kenya': 'KEN',
        'iceland': 'ISL',
        'bulgaria': 'BUL',
        'bosnia and herzegovina': 'BIH',
        'unknown': '—',
    },

    abbreviateCountry(country) {
        if (!country) return null;
        const shortened = NRWConfig.countryAbbrev[country.toLowerCase()];
        if (shortened) return shortened;
        // For unmapped countries, return as-is (capitalized)
        if (country.length <= 3) return country.toUpperCase();
        return country;
    },

    resolveService(rawName) {
        if (!rawName) return null;
        const s = rawName.toLowerCase();
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
    }
};

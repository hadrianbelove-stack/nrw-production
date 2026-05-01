/**
 * NRW Shared Config — single source of truth for service maps and utilities
 * Used by both assets/app.js (desktop) and mobile/mobile.js
 */
const NRWConfig = {
    // Streaming service definitions (colors in CSS :root variables)
    SERVICE_MAP: {
        netflix:   { class: 'netflix',   name: 'NETFLIX',    badgeName: 'NETFLIX',   btnName: 'Netflix',    matches: ['netflix'],         logo: 'netflix%20square%20logo.png' },
        max:       { class: 'max',       name: 'MAX',        badgeName: 'MAX',       btnName: 'Max',        matches: ['max', 'hbo'],      logo: 'max%20logo.jpeg' },
        disney:    { class: 'disney',    name: 'DISNEY+',    badgeName: 'DISNEY+',   btnName: 'Disney+',    matches: ['disney'],           logo: 'disney%20plus%20logo%20sqaure.jpg' },
        prime:     { class: 'prime',     name: 'PRIME VIDEO', badgeName: 'PRIME',    btnName: 'Prime',      matches: ['amazon', 'prime'],  logo: 'primevideo.png' },
        hulu:      { class: 'hulu',      name: 'HULU',       badgeName: 'HULU',      btnName: 'Hulu',       matches: ['hulu'],             logo: 'hulu%20sqaure%20logo.png' },
        peacock:   { class: 'peacock',   name: 'PEACOCK',    badgeName: 'PEACOCK',   btnName: 'Peacock',    matches: ['peacock'],           logo: 'peaccok%20logo.png' },
        mubi:      { class: 'mubi',      name: 'MUBI',       badgeName: 'MUBI',      btnName: 'MUBI',       matches: ['mubi'],             logo: 'mubi%20logo.png' },
        shudder:   { class: 'shudder',   name: 'SHUDDER',    badgeName: 'SHUDDER',   btnName: 'Shudder',    matches: ['shudder'],           logo: 'shudder%20logo.jpg' },
        criterion: { class: 'criterion', name: 'CRITERION',  badgeName: 'CRITERION', btnName: 'Criterion',  matches: ['criterion'],         logo: 'criterion%20logo%20sqaure.png' },
        tubi:      { class: 'tubi',      name: 'TUBI',       badgeName: 'TUBI',      btnName: 'Tubi',       matches: ['tubi'],             logo: 'tubi.png' },
        amc:       { class: 'amc',       name: 'AMC+',       badgeName: 'AMC+',      btnName: 'AMC+',       matches: ['amc'],              logo: 'amc-plus-logo-png_seeklogo-483819.png' },
        youtube:   { class: 'youtube',   name: 'YOUTUBE',    badgeName: 'YOUTUBE',   btnName: 'YouTube',    matches: ['youtube'] },
        paramount: { class: 'paramount', name: 'PARAMOUNT+', badgeName: 'P+',        btnName: 'Paramount+', matches: ['paramount'],         logo: 'paramoung%20plus%20logo.png' },
        kanopy:    { class: 'kanopy',    name: 'KANOPY',     badgeName: 'KANOPY',    btnName: 'Kanopy',     matches: ['kanopy'],            logo: 'kanopy.png' },
        hoopla:    { class: 'hoopla',    name: 'HOOPLA',     badgeName: 'HOOPLA',    btnName: 'Hoopla',     matches: ['hoopla'],            logo: 'hoopla.png' },
        roku:      { class: 'roku',      name: 'ROKU CH.',   badgeName: 'ROKU',      btnName: 'Roku Ch.',   matches: ['roku'],              logo: 'roku.png' },
        pluto:     { class: 'pluto',     name: 'PLUTO TV',   badgeName: 'PLUTO',     btnName: 'Pluto TV',   matches: ['pluto'],             logo: 'Pluto_TV_2020_logo.png' },
        crackle:   { class: 'crackle',   name: 'CRACKLE',    badgeName: 'CRACKLE',   btnName: 'Crackle',    matches: ['crackle'],           logo: 'Crackle-Symbol.png' },
        fawesome:  { class: 'fawesome',  name: 'FAWESOME',   badgeName: 'FAWESOME',  btnName: 'Fawesome',   matches: ['fawesome'],          logo: 'fawesome.png' },
        fandango:  { class: 'fandango',  name: 'FANDANGO',   badgeName: 'FANDANGO',  btnName: 'Fandango',   matches: ['fandango'],          logo: 'fandangoathome.png' },
    },

    // VOD (rent/buy) service definitions (colors in CSS :root variables)
    VOD_SERVICE_MAP: {
        amazon:    { key: 'amazon',    matches: ['amazon', 'prime'], label: 'AMAZON',     btnLabel: 'Rent Amazon',   logo: 'pngimg.com%20-%20amazon_PNG17.png' },
        apple:     { key: 'apple',     matches: ['apple', 'itunes'], label: 'APPLE TV',  btnLabel: 'Rent Apple TV', logo: 'apple%20logo.png' },
        fandango:  { key: 'fandango',  matches: ['fandango'],        label: 'FANDANGO',  btnLabel: 'Rent Fandango', logo: 'fandangoathome.png' },
        youtube:   { key: 'youtube',   matches: ['youtube'],         label: 'YOUTUBE',   btnLabel: 'Rent YouTube',  logo: null },
        screening: { key: 'screening', matches: ['eventive'],        label: 'BUY TICKET', btnLabel: 'Buy Ticket',  logo: null,
                     linkMatches: ['eventive.org', 'festivalplayer', 'shift72.com'] },
    },

    // Country abbreviations per STYLE_GUIDE.md
    countryAbbrev: {
        'united states of america': 'USA', 'united states': 'USA', 'usa': 'USA',
        'united kingdom': 'UK', 'great britain': 'UK',
        'south korea': 'S. Korea',
        'south africa': 'S. Africa',
        'new zealand': 'N. Zealand',
        'bosnia and herzegovina': 'Bosnia',
        'saudi arabia': 'S. Arabia'
    },

    abbreviateCountry(country) {
        if (!country) return null;
        const shortened = NRWConfig.countryAbbrev[country.toLowerCase()];
        if (shortened) return shortened;
        if (country !== country[0].toUpperCase() + country.slice(1).toLowerCase()) {
            return country[0].toUpperCase() + country.slice(1).toLowerCase();
        }
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

/**
 * NRW Shared Config — single source of truth for service maps and utilities
 * Used by both assets/app.js (desktop) and mobile/mobile.js
 */
const NRWConfig = {
    // Streaming service definitions
    SERVICE_MAP: {
        netflix:   { class: 'netflix',   name: 'NETFLIX',      badgeName: 'NETFLIX',   btnName: 'Netflix',    bg: '#E50914', text: '#fff',  matches: ['netflix'],    logo: 'netflix%20square%20logo.png' },
        max:       { class: 'max',       name: 'MAX',          badgeName: 'MAX',       btnName: 'Max',        bg: '#B537F2', text: '#fff',  matches: ['max', 'hbo'], logo: 'max%20logo.jpeg' },
        disney:    { class: 'disney',    name: 'DISNEY+',      badgeName: 'DISNEY+',   btnName: 'Disney+',    bg: '#113CCF', text: '#fff',  matches: ['disney'],     logo: 'disney%20plus%20logo%20sqaure.jpg' },
        prime:     { class: 'prime',     name: 'PRIME VIDEO',  badgeName: 'PRIME',     btnName: 'Prime',      bg: '#00A8E1', text: '#fff',  matches: ['amazon', 'prime'], logo: 'primevideo.png' },
        hulu:      { class: 'hulu',      name: 'HULU',         badgeName: 'HULU',      btnName: 'Hulu',       bg: '#1CE783', text: '#000',  matches: ['hulu'],       logo: 'hulu%20sqaure%20logo.png' },
        peacock:   { class: 'peacock',   name: 'PEACOCK',      badgeName: 'PEACOCK',   btnName: 'Peacock',    bg: '#000',    text: '#fff',  matches: ['peacock'],    logo: 'peaccok%20logo.png' },
        mubi:      { class: 'mubi',      name: 'MUBI',         badgeName: 'MUBI',      btnName: 'MUBI',       bg: '#DA2128', text: '#fff',  matches: ['mubi'],       logo: 'mubi%20logo.png' },
        shudder:   { class: 'shudder',   name: 'SHUDDER',      badgeName: 'SHUDDER',   btnName: 'Shudder',    bg: '#8B0000', text: '#fff',  matches: ['shudder'],    logo: 'shudder%20logo.jpg' },
        criterion: { class: 'criterion', name: 'CRITERION',    badgeName: 'CRITERION', btnName: 'Criterion',  bg: '#000',    text: '#fff',  matches: ['criterion'],  logo: 'criterion%20logo%20sqaure.png' },
        tubi:      { class: 'tubi',      name: 'TUBI',         badgeName: 'TUBI',      btnName: 'Tubi',       bg: '#FA382F', text: '#fff',  matches: ['tubi'],       logo: 'tubi.png' },
        amc:       { class: 'amc',       name: 'AMC+',         badgeName: 'AMC+',      btnName: 'AMC+',       bg: '#1B6FE0', text: '#fff',  matches: ['amc'],        logo: 'amc-plus-logo-png_seeklogo-483819.png' },
        youtube:   { class: 'youtube',   name: 'YOUTUBE',      badgeName: 'YOUTUBE',   btnName: 'YouTube',    bg: '#FF0000', text: '#fff',  matches: ['youtube'] },
        paramount: { class: 'paramount', name: 'PARAMOUNT+',   badgeName: 'P+',        btnName: 'Paramount+', bg: '#0064FF', text: '#fff',  matches: ['paramount'],  logo: 'paramoung%20plus%20logo.png' },
        kanopy:    { class: 'kanopy',    name: 'KANOPY',       badgeName: 'KANOPY',    btnName: 'Kanopy',     bg: '#1B7A43', text: '#fff',  matches: ['kanopy'],     logo: 'kanopy.png' },
        hoopla:    { class: 'hoopla',    name: 'HOOPLA',       badgeName: 'HOOPLA',    btnName: 'Hoopla',     bg: '#FC4F08', text: '#fff',  matches: ['hoopla'],     logo: 'hoopla.png' },
        roku:      { class: 'roku',      name: 'ROKU CH.',     badgeName: 'ROKU',      btnName: 'Roku Ch.',   bg: '#6C3A97', text: '#fff',  matches: ['roku'],       logo: 'roku.png' },
        pluto:     { class: 'pluto',     name: 'PLUTO TV',     badgeName: 'PLUTO',     btnName: 'Pluto TV',   bg: '#00B4E4', text: '#fff',  matches: ['pluto'],      logo: 'Pluto_TV_2020_logo.png' },
        crackle:   { class: 'crackle',   name: 'CRACKLE',      badgeName: 'CRACKLE',   btnName: 'Crackle',    bg: '#FF6600', text: '#fff',  matches: ['crackle'],    logo: 'Crackle-Symbol.png' },
        fawesome:  { class: 'fawesome',  name: 'FAWESOME',     badgeName: 'FAWESOME',  btnName: 'Fawesome',   bg: '#5B8DEF', text: '#fff',  matches: ['fawesome'],   logo: 'fawesome.png' },
        fandango:  { class: 'fandango',  name: 'FANDANGO',     badgeName: 'FANDANGO',  btnName: 'Fandango',   bg: '#FF6600', text: '#fff',  matches: ['fandango'],   logo: 'fandangoathome.png' },
    },

    // VOD (rent/buy) service definitions
    VOD_SERVICE_MAP: {
        amazon:    { key: 'amazon',    matches: ['amazon', 'prime'],   label: 'AMAZON',     btnLabel: 'Rent Amazon',    style: 'background:#ff9900;color:#000', logo: 'pngimg.com%20-%20amazon_PNG17.png' },
        apple:     { key: 'apple',     matches: ['apple', 'itunes'],   label: 'APPLE TV',   btnLabel: 'Rent Apple TV',  style: 'background:#000;color:#fff',    logo: 'apple%20logo.png' },
        fandango:  { key: 'fandango',  matches: ['fandango'],          label: 'FANDANGO',   btnLabel: 'Rent Fandango',  style: 'background:#FF6600;color:#fff', logo: 'fandangoathome.png' },
        youtube:   { key: 'youtube',   matches: ['youtube'],           label: 'YOUTUBE',    btnLabel: 'Rent YouTube',   style: 'background:#FF0000;color:#fff', logo: null },
        screening: { key: 'screening', matches: ['eventive'],          label: 'BUY TICKET', btnLabel: 'Buy Ticket',     style: 'background:transparent;color:#FFD700;border:2px solid #FFD700', logo: null,
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
        const shortened = this.countryAbbrev[country.toLowerCase()];
        if (shortened) return shortened;
        if (country !== country[0].toUpperCase() + country.slice(1).toLowerCase()) {
            return country[0].toUpperCase() + country.slice(1).toLowerCase();
        }
        return country;
    },

    resolveService(rawName) {
        if (!rawName) return null;
        const s = rawName.toLowerCase();
        for (const entry of Object.values(this.SERVICE_MAP)) {
            if (entry.matches.some(m => s.includes(m))) return entry;
        }
        return null;
    },

    resolveVODService(serviceName, link) {
        if (!serviceName) return null;
        const s = serviceName.toLowerCase();
        for (const entry of Object.values(this.VOD_SERVICE_MAP)) {
            if (entry.matches.some(m => s.includes(m))) return entry;
        }
        if (link) {
            for (const entry of Object.values(this.VOD_SERVICE_MAP)) {
                if (entry.linkMatches && entry.linkMatches.some(m => link.includes(m))) return entry;
            }
        }
        return null;
    }
};

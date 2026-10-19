// == Script: Anclador Autom?tico de Ligas Betplay en Flashscore ==
// Instrucciones:
// 1. Ve a https://www.flashscore.co/
// 2. Abre la consola de desarrollo (F12 -> Consola / Console)
// 3. Pega este c?digo y presiona Enter
(async function anclarLigasBetplay() {
    const BETPLAY_PATHS = new Set(["futbol/africa/liga-de-campeones-caf", "futbol/alemania/2-bundesliga", "futbol/alemania/3-liga", "futbol/alemania/bundesliga", "futbol/alemania/bundesliga-femenina", "futbol/alemania/dfb-pokal", "futbol/arabia-saudi/primera-division", "futbol/arabia-saudi/saudi-professional-league", "futbol/argentina/copa-argentina", "futbol/argentina/division-reserva", "futbol/argentina/liga-profesional", "futbol/argentina/primera-b", "futbol/argentina/primera-nacional", "futbol/argentina/torneo-federal", "futbol/armenia/premier-league", "futbol/australia/a-league", "futbol/australia/npl", "futbol/austria/2-liga", "futbol/austria/bundesliga", "futbol/austria/regionalliga-ost", "futbol/bahrein/premier-league", "futbol/belgica/1st-national", "futbol/belgica/challenger-pro-league", "futbol/belgica/copa", "futbol/belgica/jupiler-pro-league", "futbol/bolivia/division-profesional", "futbol/bosnia-y-herzegovina/premier-league", "futbol/brasil/campeonato-carioca-b1", "futbol/brasil/campeonato-carioca-u20", "futbol/brasil/campeonato-gaucho-2", "futbol/brasil/copa-de-brasil", "futbol/brasil/copa-de-brasil-femenina", "futbol/brasil/copa-do-brasil-u20", "futbol/brasil/serie-a", "futbol/brasil/serie-b", "futbol/bulgaria/parva-liga", "futbol/canada/canadian-premier-league", "futbol/canada/northern-super-league", "futbol/chile/primera-b", "futbol/chile/primera-division", "futbol/china/jia-league", "futbol/china/superliga", "futbol/china/yi-league", "futbol/colombia/copa-colombia", "futbol/colombia/primera-a", "futbol/colombia/primera-b", "futbol/corea-del-sur/k-league-1", "futbol/corea-del-sur/k-league-2", "futbol/costa-rica/liga-de-ascenso", "futbol/costa-rica/primera-division", "futbol/croacia/hnl", "futbol/dinamarca/1-division", "futbol/dinamarca/2-division", "futbol/dinamarca/3-division", "futbol/dinamarca/landspokal-cup", "futbol/dinamarca/superliga", "futbol/ecuador/liga-pro", "futbol/ecuador/liga-pro-serie-b", "futbol/egipto/premier-league", "futbol/egipto/segunda-division", "futbol/el-salvador/primera-division", "futbol/emiratos-arabes-unidos/uae-league", "futbol/escocia/championship", "futbol/escocia/league-cup", "futbol/escocia/league-one", "futbol/escocia/premiership", "futbol/escocia/scottish-cup", "futbol/escocia/swpl-1-femenina", "futbol/eslovaquia/2-liga", "futbol/eslovaquia/3-liga-west", "futbol/eslovaquia/nike-liga", "futbol/eslovenia/prva-liga", "futbol/espana/copa-del-rey", "futbol/espana/laliga-ea-sports", "futbol/espana/laliga-hypermotion", "futbol/espana/primera-division-femenina", "futbol/espana/primera-rfef-grupo-1", "futbol/espana/primera-rfef-grupo-2", "futbol/espana/segunda-rfef-grupo-1", "futbol/espana/segunda-rfef-grupo-2", "futbol/espana/segunda-rfef-grupo-5", "futbol/espana/tercera-rfef-grupo-1", "futbol/espana/tercera-rfef-grupo-4", "futbol/espana/tercera-rfef-grupo-6", "futbol/espana/tercera-rfef-grupo-7", "futbol/espana/tercera-rfef-grupo-9", "futbol/estonia/esiliiga", "futbol/estonia/esiliiga-b", "futbol/estonia/meistriliiga", "futbol/estonia/meistriliiga-femenina", "futbol/etiopia/premier-league", "futbol/europa/champions-league", "futbol/europa/conference-league", "futbol/europa/eurocopa", "futbol/europa/europa-league", "futbol/europa/uefa-nations-league", "futbol/finlandia/kansallinen-liiga-femenina", "futbol/finlandia/veikkausliiga", "futbol/finlandia/ykkonen", "futbol/finlandia/ykkosliiga", "futbol/francia/copa-de-francia", "futbol/francia/ligue-1", "futbol/francia/ligue-2", "futbol/francia/national", "futbol/francia/national-2-grupo-a", "futbol/grecia/superliga", "futbol/guatemala/liga-nacional", "futbol/honduras/liga-nacional", "futbol/hungria/merkantil-bank-liga", "futbol/hungria/otp-bank-liga", "futbol/hungria/simple-noi-liga-femenina", "futbol/india/isl", "futbol/indonesia/liga-1", "futbol/inglaterra/championship", "futbol/inglaterra/efl-cup", "futbol/inglaterra/fa-cup", "futbol/inglaterra/league-one", "futbol/inglaterra/league-two", "futbol/inglaterra/national-league", "futbol/inglaterra/national-league-north", "futbol/inglaterra/national-league-south", "futbol/inglaterra/npl-division-one-south-central", "futbol/inglaterra/premier-league", "futbol/inglaterra/women-s-super-league", "futbol/irlanda-del-norte/nifl-premiership", "futbol/irlanda/first-division", "futbol/irlanda/premier-division", "futbol/islandia/besta-deild-karla", "futbol/israel/leumit-league", "futbol/italia/copa-italia", "futbol/italia/serie-a", "futbol/italia/serie-a-femenina", "futbol/italia/serie-b", "futbol/italia/serie-c-grupo-a", "futbol/italia/serie-c-grupo-b", "futbol/italia/serie-c-grupo-c", "futbol/jamaica/premier-league", "futbol/japon/j1-league", "futbol/japon/j2-league", "futbol/japon/jfl", "futbol/japon/nadeshiko-league-femenina", "futbol/jordania/premier-league", "futbol/kazajistan/liga-premier", "futbol/letonia/virsliga", "futbol/lituania/i-lyga", "futbol/malawi/super-league", "futbol/marruecos/botola-pro", "futbol/mexico/liga-de-expansion-mx", "futbol/mexico/liga-mx", "futbol/mexico/liga-mx-femenil", "futbol/mexico/liga-mx-u23", "futbol/mexico/liga-premier-serie-a", "futbol/mundial/campeonato-del-mundo", "futbol/nicaragua/liga-primera", "futbol/nigeria/npfl", "futbol/noruega/division-2-group-1", "futbol/noruega/eliteserien", "futbol/noruega/obos-ligaen", "futbol/noruega/toppserien-femenina", "futbol/paises-bajos/eredivisie", "futbol/paises-bajos/keuken-kampioen-divisie", "futbol/paises-bajos/knvb-beker", "futbol/paraguay/copa-de-primera", "futbol/peru/liga-1", "futbol/peru/liga-2", "futbol/polonia/division-1", "futbol/polonia/ekstraklasa", "futbol/portugal/liga-next-gen-u23", "futbol/portugal/liga-portugal", "futbol/qatar/qsl", "futbol/qatar/qsl-2", "futbol/republica-checa/chance-liga", "futbol/republica-checa/chnl", "futbol/rumania/liga-3-seria-1", "futbol/rumania/superliga", "futbol/serbia/mozzart-bet-prva-liga", "futbol/serbia/super-liga", "futbol/sudafrica/betway-premiership", "futbol/sudafrica/motsepe-foundation-championship", "futbol/sudamerica/copa-libertadores", "futbol/sudamerica/copa-libertadores-femenina", "futbol/sudamerica/copa-sudamericana", "futbol/suecia/allsvenskan", "futbol/suecia/damallsvenskan", "futbol/suecia/division-2-norra-gotaland", "futbol/suecia/elitettan-femenina", "futbol/suecia/superettan", "futbol/suiza/super-league", "futbol/tailandia/thai-league-1", "futbol/tanzania/ligi-kuu-bara", "futbol/turquia/1-lig", "futbol/turquia/super-lig", "futbol/turquia/u19-league", "futbol/ucrania/premier-league", "futbol/uruguay/copa-auf-uruguay", "futbol/uruguay/primera-division", "futbol/uruguay/segunda-division", "futbol/usa/mls", "futbol/usa/mls-next-pro", "futbol/usa/nwsl-women", "futbol/usa/usl-championship", "futbol/usa/usl-league-one", "futbol/usa/usl-w-league", "futbol/venezuela/liga-futve"]);

    function cleanHref(href) {
        if (!href) return "";
        return href.replace("https://www.flashscore.co", "")
                   .split("?")[0]
                   .split("#")[0]
                   .replace(/^\/+|\/+$/g, "")
                   .toLowerCase();
    }

    function esLigaBetplay(headerEl) {
        const link = headerEl.querySelector('a.headerLeague__title');
        const href = cleanHref(link ? link.getAttribute('href') : "");
        if (!href) return false;

        // Comprobaci?n exacta o por prefijo de categor?a/torneo
        if (BETPLAY_PATHS.has(href)) return true;
        for (const p of BETPLAY_PATHS) {
            if (href.startsWith(p) || p.startsWith(href)) return true;
        }
        return false;
    }

    let totalAncladas = 0;
    let yaAncladas = 0;
    let ignoradas = 0;

    function procesarCabecerasVisibles() {
        const headers = document.querySelectorAll('.headerLeague, [data-testid="wcl-headerLeague"]');
        headers.forEach(h => {
            const pinBtn = h.querySelector('.wizard__relativeWrapper button[data-testid*="wcl-pin"], button[class*="wcl-pin"]');
            if (!pinBtn) return;

            const isPinned = pinBtn.getAttribute('data-testid') === 'wcl-pin-active' ||
                             pinBtn.getAttribute('aria-pressed') === 'true' ||
                             pinBtn.className.includes('wcl-active') ||
                             (pinBtn.getAttribute('aria-label') || '').includes('Desanclar');

            const link = h.querySelector('a.headerLeague__title');
            const country = h.querySelector('.headerLeague__category-text')?.innerText?.trim() || "";
            const league = h.querySelector('.headerLeague__title-text')?.innerText?.trim() || link?.innerText?.trim() || "";
            const nombreCompleto = country ? `${country}: ${league}` : league;

            if (esLigaBetplay(h)) {
                if (!isPinned) {
                    pinBtn.click();
                    totalAncladas++;
                    console.log(`%c[+ ANCLADA] ${nombreCompleto}`, 'color: #10b981; font-weight: bold;');
                } else {
                    yaAncladas++;
                }
            } else {
                ignoradas++;
            }
        });
    }

    console.log("%c[*] Escaneando la p?gina y anclando competiciones cubiertas por Betplay...", "color: #3b82f6; font-size: 14px; font-weight: bold;");

    // Primera pasada
    procesarCabecerasVisibles();

    // Desplazamiento suave para cargar y anclar las que cargan con lazy load
    console.log("%c[*] Desplazando p?gina para cargar ligas adicionales...", "color: #f59e0b;");
    const scrollStep = 800;
    const maxScroll = document.body.scrollHeight;
    for (let pos = 0; pos <= maxScroll; pos += scrollStep) {
        window.scrollTo(0, pos);
        await new Promise(r => setTimeout(r, 200));
        procesarCabecerasVisibles();
    }
    window.scrollTo(0, 0);

    console.log("%c" + "=".repeat(55), "color: #9ca3af;");
    console.log(`%c[RESUMEN FINAL]%c Se anclaron %c${totalAncladas}%c ligas nuevas. (${yaAncladas} ya estaban ancladas, ${ignoradas} ignoradas).`, 
        "color: #10b981; font-weight: bold; font-size: 14px;", 
        "color: #ffffff;", 
        "color: #10b981; font-weight: bold;", 
        "color: #ffffff;");
    console.log("%c" + "=".repeat(55), "color: #9ca3af;");
})();

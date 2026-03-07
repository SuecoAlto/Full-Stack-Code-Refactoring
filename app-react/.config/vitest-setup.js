/**
 * Vitest global setup-fil.
 * Refereras av vitest.config.js via setupFiles — körs innan alla tester startar.
 *
 * - '@testing-library/jest-dom': Lägger till DOM-specifika matchare till expect(),
 *   t.ex. toBeInTheDocument(), toHaveTextContent(), toBeVisible().
 *   Utan denna import finns bara grundmatchare (toBe, toEqual).
 *
 * - afterEach cleanup (körs efter varje enskilt test):
 *   - vi.clearAllTimers(): Nollställer alla setTimeout/setInterval så att
 *     timers från ett test inte läcker över till nästa.
 *   - vi.clearAllMocks(): Nollställer anropshistorik (.mock.calls, .mock.results)
 *     på alla mockar så att varje test startar med rent bord.
 *
 * Detta förhindrar att tester påverkar varandra och säkerställer pålitliga resultat.
 *
 * För en icke-teknisk person:
 * Tänk dig att varje test är som en provstation på en fabrik. Denna fil ser till
 * att stationen rensas och återställs mellan varje produkt som testas — annars
 * kan smuts från förra produkten ge falskt underkänt på nästa.
 */
import { afterEach, vi } from 'vitest';
import '@testing-library/jest-dom';

// runs a cleanup after each test case (e.g. clearing jsdom)
afterEach(() => {
    vi.clearAllTimers();
    vi.clearAllMocks();
});

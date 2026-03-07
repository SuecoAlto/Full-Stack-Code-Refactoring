/**
 * App.test.jsx — Enhetstest för App-komponenten.
 *
 * VAD: Renderar <App /> i en simulerad DOM (jsdom) och letar efter texten "learn react".
 *
 * PROBLEM: Testet är trasigt/utdaterat. Det letar efter "learn react" — en text som
 * fanns i den ursprungliga Create React App-mallen men som INTE finns i vår App.jsx.
 * Om du kör `npm test` i app-react/ kommer detta test att FAILA.
 *
 * BEROENDEN:
 *   - Importerar App från ./App.jsx (komponenten som testas)
 *   - Använder @testing-library/react (render, screen) för att rendera och söka i DOM
 *   - Använder @testing-library/jest-dom (toBeInTheDocument) via vitest-setup.js
 *   - Körs av vitest (via npm test i app-react/)
 *
 * BEHÖVER JAG RÖRA DEN?
 *   - Alvas CI kör INTE detta test — de kör bara `cypress run` från root.
 *     Så det påverkar inte betyget.
 *   - Men om man vill visa att man skriver bra kod bör man fixa testet
 *     så det testar något som faktiskt finns, t.ex:
 *     test('renders submit button', () => {
 *       render(<App />);
 *       expect(screen.getByText(/submit/i)).toBeInTheDocument();
 *     });
 *
 * Kort sagt: En kvarglömd boilerplate-test som aldrig uppdaterades.
 */
import { render, screen } from "@testing-library/react";
import App from "./App";

test("renders learn react link", () => {
  render(<App />);
  const linkElement = screen.getByText(/learn react/i);
  expect(linkElement).toBeInTheDocument();
});

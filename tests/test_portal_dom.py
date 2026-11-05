import unittest

from ava_py.browser import portal_wl_cards


class PortalCardsTest(unittest.TestCase):
    def test_reads_wl_label_above_course_title(self):
        from playwright.sync_api import sync_playwright

        html = """
        <section>
          <article class="card">
            <span>Aula Modelo Institucional - WL</span>
            <h3>Análise de Computabilidade<br>e Complexidade de<br>Algoritmos</h3>
            <a href="/open/1">ACESSAR A DISCIPLINA</a>
          </article>
          <article class="card">
            <span>Aula Modelo Institucional - Presencial</span>
            <h3>Outra Matéria</h3>
            <a href="/open/2">ACESSAR A DISCIPLINA</a>
          </article>
        </section>
        """
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            try:
                page = browser.new_page()
                page.set_content(html)
                self.assertEqual(
                    portal_wl_cards(page),
                    ["Análise de Computabilidade e Complexidade de Algoritmos"],
                )
                page.set_content("""
                <section>
                  <article><p>Outro curso</p><a>ACESSAR A DISCIPLINA</a></article>
                  <article>
                    <div><span>Disciplinas Híbridas HAMI - WL</span></div>
                    <div><h3>Computação Gráfica e Processamento de Imagens</h3></div>
                    <a>AGUARDE</a>
                  </article>
                </section>
                """)
                self.assertEqual(portal_wl_cards(page), ["Computação Gráfica e Processamento de Imagens"])
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()

# Style-Recherche · Storybook / Duolingo-inspiriert

**Ziel:** Light-UI im Geist der Referenz, aber mit eigenen Vektoren, eigenem Pawn-Mascot und ohne fremde Logos/Assets.

## Kurz recherchiert

- Offizielles Design-Portal: <https://design.duolingo.com/> (Redirect auf Duolingo Design Blog).
- Community-Design-System-Referenz bestätigt `#58cc02` Feather Green, `#1cb0f6` Macaw Blue, `#4b4b4b` Eel Text, `#777777` Wolf Secondary, `#ffffff` Snow, `#f7f7f7` Polar, 12px Default-Radius, 16px Large-Radius, 8px-Spacing-Raster und `0 4px 0` Button-Lip: <https://www.designsystems.one/design-systems/duolingo-design>
- Zusätzliche Design-System-Zusammenfassung bestätigt Feather/DIN Next Rounded, 2px Outlines, 12px Radius, grüne CTA mit `#58a700` Lip: <https://oh-my-design.kr/design-systems/duolingo>
- Font-Hintergrund: Feather Bold / DIN Next Rounded / Nunito-ähnliche Fallbacks: <https://welovedaily.net/article/duolingo-brand-identity-mascot-strategy>

## Umgesetzte Tokens

| Rolle | Wert | Verwendung |
|---|---|---|
| Paper White | `#ffffff` | Fenster, Karten, helle Felder |
| Polar | `#f7f7f7` | Panel2, Code/Listen-Hintergrund |
| Storybook Green | `#d7ffb8` | Surface-Tint, Sticker-Shades, Mascot-Kreis |
| Fresh Leaf | `#a5ed6e` | dunkle Brettfelder (klarer Kontrast zu Weiß, verhindert „komplett grün“) |
| Eager Green | `#58cc02` | Akzent, CTA, Rahmen, Eval-Bar |
| Green Lip | `#58a700` | Button-Lip, aktive Uhr, Koordinaten |
| Spark Blue | `#1cb0f6` | Pfeile, sekundäre Piece-Akzente |
| Night Ink | `#000437` | dicke Piece-Outlines, Mascot-Linien |
| Charcoal | `#4b4b4b` | Primärtext |
| Pencil Gray | `#777777` | Sekundärtext |
| Faded Gray | `#afafaf` | 2px Borders |
| Bee Yellow | `#ffc800` | Last-Move / Selection |
| Cardinal Red | `#ff4b4b` | Schach / Low-Time |

**Typografie:** `"Nunito", "Arial Rounded MT Bold", "Segoe UI", system-ui` im Browser; Tk nutzt `Segoe UI` (Windows) / `DejaVu Sans` (Ubuntu) mit `bold`. Keine externen Fonts.

**Shapes:** 12px Buttons, 16px Cards, 2px Outlines, 4px Button-Lip, keine Gradienten/Glass/Soft-Shadows.

**Figures:** flache 2D-Sticker mit 3.8px Night-Ink-Outline, Storybook-Green/Blue-Shades, kleiner Akzentbogen und Akzentpunkt. Keine Raster-Assets von Duolingo/Chess.com.

## Figuren-Redesign v6.2

Die 6 Silhouetten wurden nochmals neu gezeichnet: König mit Kreuz, Dame mit 5-zackiger Krone, Turm mit Zinnen, Läufer mit Mützen-Schlitz, Springer mit Pferdekopf/Auge, Bauer mit rundem Kopf. Alle haben kleine Gesichter, 3,8 px Night-Ink-Outline, frische Akzent-Marken und einen Sparkle in der `textured`-Variante. Quelle bleibt `web/index.html`; `tools/generate_assets.js` + `tools/render_assets.py` schreiben nur `assets/pieces.zip`.

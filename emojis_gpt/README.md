# KYOKA Emoji Assets (GPT Pack)

This directory is the source catalog for KYOKA's emoji pack. It includes a compact professional dark/metallic-gold style and 60 extra icon concepts. The generated local ZIP pack contains 92 static PNGs and 8 GIFs; this repo catalog also records the expanded set.

## Asset files
- `extra_emoji_sheet.svg`: transparent SVG source sheet containing 60 additional icons (catalog preview/source).
- `extra_emoji_manifest.json`: names, categories, glyph fallbacks, and use notes.
- `emojis_gpt.zip`: the complete PNG/GIF package should be added here when binary upload is available.

## Upload workflow
1. Download the ZIP pack from the ChatGPT conversation.
2. Extract and upload the PNG/GIF files individually to Discord.
3. Replace placeholder IDs in the bot emoji registry with the resulting Discord emoji IDs.
4. Use animated IDs only for GIF emojis; keep static fallbacks.

## Style
Charcoal/black, white/silver, and metallic gold; transparent assets; crisp silhouettes; minimal decoration; readable at 32–64px. Animations are subtle and reserved for loading, music, premium, activity, and status indicators.

Do not hardcode emoji IDs across cogs. Use a central registry and gracefully fall back to text/Unicode when an emoji is missing.

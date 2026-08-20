# XPath recipes for Calibre and EPUB

## Namespace map

| Prefix | URI | Used for |
|---|---|---|
| `h` | `http://www.w3.org/1999/xhtml` | XHTML content and EPUB 3 nav |
| `epub` | `http://www.idpf.org/2007/ops` | `epub:type` attributes |
| `opf` | `http://www.idpf.org/2007/opf` | EPUB package document |
| `dc` | `http://purl.org/dc/elements/1.1/` | Dublin Core metadata |
| `ncx` | `http://www.daisy.org/z3986/2005/ncx/` | EPUB 2 navigation |
| `re` | `http://exslt.org/regular-expressions` | Calibre/lxml regex extension |
| `svg` | `http://www.w3.org/2000/svg` | SVG content |
| `m` | `http://www.w3.org/1998/Math/MathML` | MathML content |

Default XML namespaces do not apply to unprefixed XPath names. The XPath prefix is chosen by the
caller and need not equal the source document's prefix.

## Calibre structure detection

All level-one and level-two headings:

```xpath
//h:h1 | //h:h2
```

Heading with a `chapter` class token:

```xpath
//*[self::h:h1 or self::h:h2][contains(concat(' ', normalize-space(@class), ' '), ' chapter ')]
```

Numbered or named chapter headings, case-insensitive:

```xpath
//h:h1[re:test(normalize-space(.), '^(chapter|part|book|section)\b', 'i')]
| //h:h2[re:test(normalize-space(.), '^(chapter|part|book|section)\b', 'i')]
```

First main-body heading with stable IDs:

```xpath
(//h:*[self::h:h1 or self::h:h2][starts-with(@id, 'chapter')])[1]
```

TOC levels when heading markup is reliable:

```text
--level1-toc //h:h1
--level2-toc //h:h2
--level3-toc //h:h3
```

Use separate expressions per level. A union does not preserve semantic nesting by itself.

## EPUB 3 navigation

```xpath
//h:nav[@epub:type='toc']//h:a
//h:nav[@epub:type='landmarks']//h:a
//h:nav[@epub:type='page-list']//h:a
```

If `epub:type` can contain multiple values:

```xpath
//h:nav[contains(concat(' ', normalize-space(@epub:type), ' '), ' toc ')]//h:a
```

## OPF package document

```xpath
//opf:manifest/opf:item[@media-type='application/xhtml+xml']
//opf:manifest/opf:item[contains(concat(' ', normalize-space(@properties), ' '), ' nav ')]
//opf:spine/opf:itemref/@idref
//opf:spine/opf:itemref[@linear='no']/@idref
/opf:package/opf:metadata/dc:title
```

## EPUB 2 NCX

```xpath
//ncx:navMap//ncx:navPoint/ncx:navLabel/ncx:text
//ncx:navMap//ncx:navPoint/ncx:content/@src
```

## Diagnostics

| Symptom | Likely cause | Check |
|---|---|---|
| zero XHTML matches | missing `h:` prefix | inspect root namespace and retry with `h:` |
| zero OPF/NCX matches | wrong edition namespace | print root expanded name and override `--ns` |
| far too many matches | substring class/text predicate | use token matching or anchor regex |
| valid in browser, invalid in Calibre | XPath 2+/HTML DOM assumption | reduce to XPath 1.0 and namespaced XML |
| chapter option rejected | expression returns strings/attributes | add `--require-elements` and select elements |
| correct nodes, wrong TOC nesting | one union used for all levels | use level1/2/3 expressions separately |
| shell changes expression | quoting layer consumed quotes/pipes | pass the XPath as one quoted argument |

Calibre's option reference says chapter and TOC expressions must select elements. Verify the active
version with `ebook-convert input.ext output.ext -h` because options depend on both formats.

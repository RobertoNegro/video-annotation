from pygments import highlight, lexers, formatters


def json_to_html(json):
    return '<style>' + formatters.HtmlFormatter().get_style_defs() + '</style>' + highlight(json, lexers.JsonLexer(),
                     formatters.HtmlFormatter())

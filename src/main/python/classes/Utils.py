from pygments import highlight, lexers, formatters


def json_to_html(json):
    return highlight(json, lexers.JsonLexer(),
                     formatters.HtmlFormatter()) + '<style>' + formatters.HtmlFormatter().get_style_defs() + '</style>'

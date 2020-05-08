import logging
import sys
import coloredlogs


def add_logging_event(name, num):
    method_name = name.lower()

    if hasattr(logging, name):
        raise AttributeError('{} already defined in logging module'.format(name))
    if hasattr(logging, method_name):
        raise AttributeError('{} already defined in logging module'.format(method_name))
    if hasattr(logging.getLoggerClass(), method_name):
        raise AttributeError('{} already defined in logger class'.format(method_name))

    def log_for_level(self, message, *args, **kwargs):
        if self.isEnabledFor(num):
            self._log(num, message, args, **kwargs)

    def log_to_root(message, *args, **kwargs):
        logging.log(num, message, *args, **kwargs)

    logging.addLevelName(num, name)
    setattr(logging, name, num)
    setattr(logging.getLoggerClass(), method_name, log_for_level)
    setattr(logging, method_name, log_to_root)


CAN_USE_BOLD_FONT = (not sys.platform.startswith('win'))
level_styles = dict(
    render=dict(color='white', faint=True),
    player=dict(color='white', faint=True),
    spam=dict(color='green', faint=True),
    debug=dict(color='green'),
    verbose=dict(color='blue'),
    info=dict(),
    notice=dict(color='magenta'),
    warning=dict(color='yellow'),
    success=dict(color='green', bold=CAN_USE_BOLD_FONT),
    error=dict(color='red'),
    critical=dict(color='red', bold=CAN_USE_BOLD_FONT))


add_logging_event('PLAYER', 2)
add_logging_event('RENDER', 1)
coloredlogs.install(level=logging.DEBUG, milliseconds=True, level_styles=level_styles)


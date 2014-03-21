from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.common.exceptions import NoSuchElementException

from mailpile.httpd import HttpWorker
from tests import MailPileUnittest, get_shared_mailpile


class SeleniumScreenshotOnExceptionAspecter(type):
    """Wraps all methods starting with *test* with a screenshot aspect.

      The screenshot file is named *methodname*_screenshot.png.

      Notes:
        This class defines a type that has to be used as a metaclass:

         >>> class Foobar()
         ...    __metaclass__ = SeleniumScreenshotOnExceptionAspecter
         ...
         ...    def take_screenshot(self, filename):
         ...        # take screenshot
         ...        pass

         The class has to provide a take_screenshot(filename) method

      Attributes:
        none
    """

    def __new__(mcs, name, bases, dict):
        for key, value in dict.items():
            if (hasattr(value, "__call__")
                    and key != "__metaclass__"
                    and key.startswith('test')):
                dict[key] = SeleniumScreenshotOnExceptionAspecter.wrap_method(
                    value)
        return super(SeleniumScreenshotOnExceptionAspecter,
                     mcs).__new__(mcs, name, bases, dict)

    @classmethod
    def wrap_method(mcs, method):
        """Wraps method with a screenshot on exception aspect."""
        # method name has to start with test, otherwise unittest runner
        # won't detect it
        def test_call_wrapper_method(*args, **kw):
            """The wrapper method

              Notes:
                The method name has to start with *test*, otherwise the
                unittest runner won't detect is as a test method

              Args:
                *args: Variable argument list of original method
                **kw: Arbitrary keyword arguments of the original method

              Returns:
                The result of the original method call
            """
            try:
                results = method(*args, **kw)
            except:
                test_self = args[0]
                filename = '%s_screenshot.png' % method.__name__
                test_self.take_screenshot(filename)
                raise

            return results

        return test_call_wrapper_method


class MailpileSeleniumTest(MailPileUnittest):
    """Base class for all selenium GUI tests


        Attributes:
            DRIVER (WebDriver): The webdriver instance

        Examples:

        >>> class Sometest(MailpileSeleniumTest):
        ...
        ...     def test_something(self):
        ...         self.go_to_mailpile_home()
        ...         self.take_screenshot('screen.png')
        ...         self.dump_source_to('source.html')
        ...
        ...         self.navigate_to('Contacts')
        ...
        ...         self.driver.save_screenshot('screen2.png')
        ...         self.assertIn('Contacts', self.driver.title)
    """
    __metaclass__ = SeleniumScreenshotOnExceptionAspecter

    DRIVER = None

    def __init__(self, *args, **kwargs):
        MailPileUnittest.__init__(self, *args, **kwargs)

    def setUp(self):
        self.driver = self.__class__.DRIVER

    def tearDown(self):
        #        try:
        #            self.driver.close()
        #        except WebDriverException:
        #            pass
        pass

    @classmethod
    def _get_mailpile_sspec(cls):
        config = get_shared_mailpile()._config
        return (config.sys.http_host, config.sys.http_port)

    @classmethod
    def _get_mailpile_url(cls):
        return 'http://%s:%s/' % cls._get_mailpile_sspec()

    @classmethod
    def _start_web_server(cls):
        mp = get_shared_mailpile()
        session = mp._session
        config = mp._config
        sspec = cls._get_mailpile_sspec()
        cls.http_worker = config.http_worker = HttpWorker(session, sspec)
        config.http_worker.start()

    @classmethod
    def _start_selenium_driver(cls):
        if not cls.DRIVER:
            driver = webdriver.PhantomJS()  # or add to your PATH
            driver.set_window_size(1024, 768)  # optional
            cls.DRIVER = driver

    @classmethod
    def _stop_selenium_driver(cls):
        if cls.DRIVER:
            try:
                cls.DRIVER.quit()
                cls.DRIVER = None
            except WebDriverException:
                pass

    @classmethod
    def setUpClass(cls):
        cls._start_selenium_driver()
        cls._start_web_server()

    @classmethod
    def _stop_web_server(cls):
        mp = get_shared_mailpile()
        mp._config.http_worker = None
        cls.http_worker.quit()
        cls.http_worker = None

    @classmethod
    def tearDownClass(cls):
        cls._stop_web_server()
        cls._stop_selenium_driver()

    def go_to_mailpile_home(self):
        self.driver.get(self._get_mailpile_url())

    def take_screenshot(self, filename):
        try:
            self.driver.save_screenshot(filename)  # save a screenshot to disk
        except WebDriverException:
            pass

    def dump_source_to(self, filename):
        with open(filename, 'w') as out:
            out.write(self.driver.page_source.encode('utf8'))

    def navigate_to(self, name):
        contacts = self.driver.find_element_by_xpath(
            '//a[@alt="%s"]/span' % name)
        self.assertTrue(contacts.is_displayed())
        contacts.click()

    def submit_form(self, form_id):
        form = self.driver.find_element_by_id(form_id)
        form.submit()

    def write_to_input(self, field, text):
        input_field = self.driver.find_element_by_name(field)
        input_field.send_keys(text)

    def assert_link_with_text(self, text):
        try:
            self.driver.find_element_by_link_text(text)
        except NoSuchElementException:
            raise AssertionError

    def click_button_with_id(self, button_id):
        btn = self.driver.find_element_by_id(button_id)
        btn.click()

try:
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException, StaleElementReferenceException
    from selenium.common.exceptions import NoSuchElementException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.wait import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    pass

from mailpile.httpd import HttpWorker
from mailpile.tests import MailPileUnittest, get_shared_mailpile

from mailpile.safe_popen import MakePopenUnsafe

MakePopenUnsafe()


class ElementHasClass(object):
    def __init__(self, locator_tuple, class_name):
        self.locator = locator_tuple
        self.class_name = class_name

    def __call__(self, driver):
        try:
            e = driver.find_element(self.locator[0], self.locator[1])
            return self.class_name in e.get_attribute('class')
        except (NoSuchElementException, StaleElementReferenceException):
            return False


class ElementHasNotClass(object):
    def __init__(self, locator_tuple, class_name):
        self.locator = locator_tuple
        self.class_name = class_name

    def __call__(self, driver):
        try:
            e = driver.find_element(self.locator[0], self.locator[1])
            return self.class_name not in e.get_attribute('class')
        except (NoSuchElementException, StaleElementReferenceException):
            return True


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
    http_worker = None

    def __init__(self, *args, **kwargs):
        MailPileUnittest.__init__(self, *args, **kwargs)

    def setUp(self):
        self.driver = MailpileSeleniumTest.DRIVER

    def tearDown(self):
        #        try:
        #            self.driver.close()
        #        except WebDriverException:
        #            pass
        pass

    @classmethod
    def _get_mailpile_sspec(cls):
        (_, _, config, _) = get_shared_mailpile()
        return (config.sys.http_host, config.sys.http_port)

    @classmethod
    def _get_mailpile_url(cls):
        return 'http://%s:%s' % cls._get_mailpile_sspec()

    @classmethod
    def _start_web_server(cls):
        if not MailpileSeleniumTest.http_worker:
            (mp, session, config, _) = get_shared_mailpile()
            sspec = MailpileSeleniumTest._get_mailpile_sspec()
            MailpileSeleniumTest.http_worker = config.http_worker = HttpWorker(session, sspec)
            config.http_worker.start()

    @classmethod
    def _start_selenium_driver(cls):
        if not MailpileSeleniumTest.DRIVER:
            driver = webdriver.PhantomJS()  # or add to your PATH
            driver.set_window_size(1280, 1024)  # optional
            driver.implicitly_wait(5)
            driver.set_page_load_timeout(5)
            MailpileSeleniumTest.DRIVER = driver

    @classmethod
    def _stop_selenium_driver(cls):
        if MailpileSeleniumTest.DRIVER:
            try:
                MailpileSeleniumTest.DRIVER.quit()
                MailpileSeleniumTest.DRIVER = None
            except WebDriverException:
                pass

    @classmethod
    def setUpClass(cls):
        return  # FIXME: Test disabled

        MailpileSeleniumTest._start_selenium_driver()
        MailpileSeleniumTest._start_web_server()

    @classmethod
    def _stop_web_server(cls):
        if MailpileSeleniumTest.http_worker:
            (mp, _, config, _) = get_shared_mailpile()
            mp._config.http_worker = None
            MailpileSeleniumTest.http_worker.quit()
            MailpileSeleniumTest.http_worker = MailpileSeleniumTest.http_worker = None

    @classmethod
    def tearDownClass(cls):
        return  # FIXME: Test disabled

        MailpileSeleniumTest._stop_web_server()
        MailpileSeleniumTest._stop_selenium_driver()

    def go_to_mailpile_home(self):
        self.driver.get('%s/in/inbox' % self._get_mailpile_url())

    def take_screenshot(self, filename):
        try:
            self.driver.save_screenshot(filename)  # save a screenshot to disk
        except WebDriverException:
            pass

    def dump_source_to(self, filename):
        with open(filename, 'w') as out:
            out.write(self.driver.page_source.encode('utf8'))

    def navigate_to(self, name):
        contacts = self.find_element_by_xpath(
            '//a[@alt="%s"]/span' % name)
        self.assertTrue(contacts.is_displayed())
        contacts.click()

    def submit_form(self, form_id):
        form = self.driver.find_element_by_id(form_id)
        form.submit()

    def fill_form_field(self, field, text):
        input_field = self.driver.find_element_by_name(field)
        input_field.send_keys(text)

    def assert_link_with_text(self, text):
        try:
            self.driver.find_element_by_link_text(text)
        except NoSuchElementException:
            raise AssertionError

    def click_element_with_link_text(self, text):
        try:
            self.driver.find_element_by_link_text(text).click()
        except NoSuchElementException:
            raise AssertionError

    def click_element_with_id(self, element_id):
        self.driver.find_element_by_id(element_id).click()

    def click_element_with_class(self, class_name):
        self.driver.find_element_by_class_name(class_name).click()

    def page_title(self):
        return self.driver.title

    def find_element_by_id(self, id):
        return self.driver.find_element_by_id(id)

    def find_element_containing_text(self, text):
        return self.driver.find_element_by_xpath("//*[contains(.,'%s')]" % text)

    def find_element_by_xpath(self, xpath):
        return self.driver.find_element_by_xpath(xpath)

    def find_element_by_class_name(self, class_name):
        return self.driver.find_element_by_class_name(class_name)

    def assert_text(self, text):
        self.find_element_containing_text(text)

    def wait_until_element_is_visible(self, element_id):
        self.wait_until_element_is_visible_by_locator((By.ID, element_id))

    def wait_until_element_is_visible_by_locator(self, locator_tuple):
        wait = WebDriverWait(self.driver, 10)
        wait.until(EC.visibility_of_element_located(locator_tuple))

    def wait_until_element_is_invisible_by_locator(self, locator_tuple):
        wait = WebDriverWait(self.driver, 10)
        wait.until(EC.invisibility_of_element_located(locator_tuple))

    def wait_until_element_has_class(self, locator_tuple, class_name):
        self.wait_for_element_condition(ElementHasClass(locator_tuple, class_name))

    def wait_until_element_has_not_class(self, locator_tuple, class_name):
        self.wait_for_element_condition(ElementHasNotClass(locator_tuple, class_name))

    def wait_for_element_condition(self, expected_conditions):
        wait = WebDriverWait(self.driver, 10)
        wait.until(expected_conditions)

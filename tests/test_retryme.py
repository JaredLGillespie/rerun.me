# MIT License
#
# Copyright (c) 2018 Jared Gillespie
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import unittest
from unittest.mock import Mock, patch
from inspect import isclass
from functools import partial, partialmethod
from rerunme import MaxRetryError, rerunme, constant, linear, exponential, fibonacci


# Test helpers
def func_iter(iterable, *args, **kwargs):
    val = next(iterable)
    if isclass(val) and issubclass(val, Exception):
        raise val
    return val


partial_func_iter = partial(func_iter)


class Dummy:

    @classmethod
    def class_func_iter(cls, iterable):
        return func_iter(iterable)

    @staticmethod
    def static_func_iter(iterable):
        return func_iter(iterable)

    def func_iter(self, iterable):
        return func_iter(iterable)

    partial_func_iter = partialmethod(func_iter)


class TestRerunMe(unittest.TestCase):

    def test_no_handlers_success(self):
        iterable = iter([1])
        out = rerunme()(func_iter)(iterable)
        self.assertEqual(1, out)

    def test_no_handlers_error(self):
        iterable = iter([ValueError])

        with self.assertRaises(ValueError):
            rerunme()(func_iter)(iterable)

    def test_on_delay_int(self):
        iterable = iter([0, 1])
        on_delay = 0
        on_return = 0

        out = rerunme(on_delay=on_delay, on_return=on_return)(func_iter)(iterable)
        self.assertEqual(1, out)

    def test_on_delay_iterable(self):
        iterable = iter([0, 1])
        on_delay = [0]
        on_return = 0

        out = rerunme(on_delay=on_delay, on_return=on_return)(func_iter)(iterable)
        self.assertEqual(1, out)

    def test_on_delay_function(self):
        iterable = iter([0, 1])
        on_delay = lambda: [0]
        on_return = 0

        out = rerunme(on_delay=on_delay, on_return=on_return)(func_iter)(iterable)
        self.assertEqual(1, out)

    def test_on_error_is_function_handled(self):
        iterable = iter([ValueError, 1])
        on_error = lambda x: isinstance(x, ValueError)
        on_delay = [0]
        out = rerunme(on_delay=on_delay, on_error=on_error)(func_iter)(iterable)
        self.assertEqual(1, out)

    def test_on_error_is_function_unhandled(self):
        iterable = iter([ValueError])
        on_error = lambda x: not isinstance(x, ValueError)

        with self.assertRaises(ValueError):
            rerunme(on_error=on_error)(func_iter)(iterable)

    def test_on_error_is_iterable_handled(self):
        iterable = iter([ValueError, 1])
        on_error = [ValueError, TypeError]
        on_delay = [0]
        out = rerunme(on_delay=on_delay, on_error=on_error)(func_iter)(iterable)
        self.assertEqual(1, out)

    def test_on_error_is_iterable_unhandled(self):
        iterable = iter([ValueError])
        on_error = [KeyError, TypeError]

        with self.assertRaises(ValueError):
            rerunme(on_error=on_error)(func_iter)(iterable)

    def test_on_error_is_error_handled(self):
        iterable = iter([ValueError, ValueError, 1])
        on_error = ValueError
        on_delay = [0, 0]
        out = rerunme(on_delay=on_delay, on_error=on_error)(func_iter)(iterable)
        self.assertEqual(1, out)

    def test_on_error_is_error_unhandled(self):
        iterable = iter([TypeError, ValueError])
        on_error = TypeError
        on_delay = [0]

        with self.assertRaises(ValueError):
            rerunme(on_delay=on_delay, on_error=on_error)(func_iter)(iterable)

    def test_on_return_is_function_handled(self):
        iterable = iter([1, 2, 3, 4])
        on_return = lambda x: x in (1, 2, 3)
        on_delay = [0, 0, 0]
        out = rerunme(on_delay=on_delay, on_return=on_return)(func_iter)(iterable)
        self.assertEqual(4, out)

    def test_on_return_is_function_unhandled(self):
        iterable = iter([1])
        on_return = lambda x: x == 4
        out = rerunme(on_return=on_return)(func_iter)(iterable)
        self.assertEqual(out, 1)

    def test_on_return_is_iterable_handled(self):
        iterable = iter([1, 2, 3, 4])
        on_return = [1, 2, 3]
        on_delay = [0, 0, 0]
        out = rerunme(on_delay=on_delay, on_return=on_return)(func_iter)(iterable)
        self.assertEqual(4, out)

    def test_on_return_is_iterable_unhandled(self):
        iterable = iter([1])
        on_return = [4]
        out = rerunme(on_return=on_return)(func_iter)(iterable)
        self.assertEqual(out, 1)

    def test_on_return_is_value_handled(self):
        iterable = iter([1, 1, 0])
        on_return = 1
        on_delay = [0, 0]
        out = rerunme(on_delay=on_delay, on_return=on_return)(func_iter)(iterable)
        self.assertEqual(0, out)

    def test_on_return_is_value_unhandled(self):
        iterable = iter([1])
        on_return = 4
        out = rerunme(on_return=on_return)(func_iter)(iterable)
        self.assertEqual(out, 1)

    def test_on_retry_after_delay(self):
        iterable = iter([1, 2])
        on_retry = Mock()
        on_return = 1
        on_delay = [0]

        with patch('rerunme.sleep') as sleep_mock:
            rerunme(on_delay=on_delay, on_return=on_return, on_retry=on_retry, retry_after_delay=True)(func_iter)(iterable)
            sleep_mock.assert_called_once_with(0)
            on_retry.assert_called_once_with(0, 1)

    def test_on_retry_before_delay(self):
        iterable = iter([1, 2])
        on_retry = Mock(side_effect=Exception)
        on_return = 1
        on_delay = [0]

        with patch('rerunme.sleep') as sleep_mock:
            with self.assertRaises(Exception):
                rerunme(on_delay=on_delay, on_return=on_return, on_retry=on_retry, retry_after_delay=False)(func_iter)(iterable)
            sleep_mock.assert_not_called()

    def test_partial_success(self):
        iterable = iter([1, 0])
        on_return = 1
        on_error = KeyError
        on_delay = [0]
        out = rerunme(on_delay=on_delay, on_error=on_error, on_return=on_return)(partial_func_iter)(iterable)
        self.assertEqual(0, out)

    def test_partial_failure(self):
        iterable = iter([1])
        on_return = 1

        with self.assertRaises(MaxRetryError):
            rerunme(on_return=on_return)(partial_func_iter)(iterable)

    def test_method(self):
        iterable = iter([1, 0])
        on_return = 1
        on_error = KeyError
        on_delay = [0]
        out = rerunme(on_delay=on_delay, on_error=on_error, on_return=on_return)(Dummy().func_iter)(iterable)
        self.assertEqual(0, out)

    def test_class_method(self):
        iterable = iter([1, 0])
        on_return = 1
        on_error = KeyError
        on_delay = [0]
        out = rerunme(on_delay=on_delay, on_error=on_error, on_return=on_return)(Dummy.class_func_iter)(iterable)
        self.assertEqual(0, out)

    def test_static_method(self):
        iterable = iter([1, 0])
        on_return = 1
        on_error = KeyError
        on_delay = [0]
        out = rerunme(on_delay=on_delay, on_error=on_error, on_return=on_return)(Dummy.static_func_iter)(iterable)
        self.assertEqual(0, out)

    def test_partial_method(self):
        iterable = iter([1, 0])
        on_return = 1
        on_error = KeyError
        on_delay = [0]
        out = rerunme(on_delay=on_delay, on_error=on_error, on_return=on_return)(Dummy().partial_func_iter)(iterable)
        self.assertEqual(0, out)

    def test_max_retry_error_with_delay(self):
        iterable = iter([1, 0])
        on_return = lambda x: x in (1, 0)
        on_delay = [0]

        with self.assertRaises(MaxRetryError):
            rerunme(on_delay=on_delay, on_return=on_return)(func_iter)(iterable)

    def test_max_retry_error_without_delay(self):
        iterable = iter([0])
        on_return = 0

        with self.assertRaises(MaxRetryError):
            rerunme(on_return=on_return)(func_iter)(iterable)

    def test_run(self):
        on_return = [1, 2]
        on_error = KeyError
        on_delay = [0]

        decorator = rerunme(on_delay=on_delay, on_error=on_error, on_return=on_return)
        out = decorator.run(func_iter, iter([1, 0]))
        self.assertEqual(0, out)

        out = decorator.run(func_iter, iter([2, 0]))
        self.assertEqual(0, out)

    def test_handler_with_args(self):
        iterable = iter([ValueError, None])
        on_delay = [0]

        def on_error(x, *args):
            self.assertEqual(len(args), 1)
            return isinstance(x, ValueError)

        out = rerunme(on_delay=on_delay, on_error=on_error)(func_iter)(iterable)
        self.assertEqual(None, out)

    def test_handler_with_args_and_kwargs(self):
        iterable = iter([1, 0])
        on_delay = [0]

        def on_return(x, *args, **kwargs):
            self.assertEqual(len(args), 1)
            self.assertEqual(len(kwargs), 1)
            return x == 1

        out = rerunme(on_delay=on_delay, on_return=on_return)(func_iter)(iterable, nothing=True)
        self.assertEqual(0, out)

    def test_function_kwarg_only_params(self):
        iterable = iter([1, 0])

        def on_delay(*args, x=1, **kwargs):
            return x

        out = rerunme(on_delay=on_delay)(func_iter)(iterable)
        self.assertEqual(1, out)


class TestConstant(unittest.TestCase):

    def test_negative_delay(self):
        delay, limit = -1, 1
        with self.assertRaises(ValueError):
            list(constant(delay, limit)())

    def test_zero_delay(self):
        delay, limit = 0, 1
        out = list(constant(delay, limit)())
        self.assertEqual([0], out)

    def test_negative_limit(self):
        delay, limit = 1, -1
        with self.assertRaises(ValueError):
            list(constant(delay, limit)())

    def test_zero_limit(self):
        delay, limit = 1, 0
        out = list(constant(delay, limit)())
        self.assertEqual([], out)

    def test_valid(self):
        delay, limit = 2, 3
        out = list(constant(delay, limit)())
        self.assertEqual([2, 2, 2], out)


class TestLinear(unittest.TestCase):

    def test_negative_start(self):
        start, increment, limit = -1, 1, 1
        with self.assertRaises(ValueError):
            list(linear(start, increment, limit)())

    def test_zero_start(self):
        start, increment, limit = 0, 1, 1
        out = list(linear(start, increment, limit)())
        self.assertEqual([0], out)

    def test_negative_limit(self):
        start, increment, limit = 1, 1, -1
        with self.assertRaises(ValueError):
            list(linear(start, increment, limit)())

    def test_zero_limit(self):
        start, increment, limit = 1, 1, 0
        out = list(linear(start, increment, limit)())
        self.assertEqual([], out)

    def test_valid(self):
        start, increment, limit = 1, 1, 3
        out = list(linear(start, increment, limit)())
        self.assertEqual([1, 2, 3], out)

    def test_negative_increment_positive_result(self):
        start, increment, limit = 4, -1, 4
        out = list(linear(start, increment, limit)())
        self.assertEqual([4, 3, 2, 1], out)

    def test_negative_increment_negative_result(self):
        start, increment, limit = 2, -1, 4
        with self.assertRaises(ValueError):
            list(linear(start, increment, limit)())


class TestExponential(unittest.TestCase):

    def test_negative_base(self):
        base, multiplier, limit = -1, 1, 1
        with self.assertRaises(ValueError):
            list(exponential(base, multiplier, limit)())

    def test_zero_base(self):
        base, multiplier, limit = 0, 1, 2
        out = list(exponential(base, multiplier, limit)())
        self.assertEqual([1, 0], out)

    def test_negative_multiplier(self):
        base, multiplier, limit = 1, -1, 1
        with self.assertRaises(ValueError):
            list(exponential(base, multiplier, limit)())

    def test_zero_multiplier(self):
        base, multiplier, limit = 1, 0, 2
        out = list(exponential(base, multiplier, limit)())
        self.assertEqual([0, 0], out)

    def test_negative_limit(self):
        base, multiplier, limit = 1, 1, -1
        with self.assertRaises(ValueError):
            list(exponential(base, multiplier, limit)())

    def test_zero_limit(self):
        base, multiplier, limit = 1, 1, 0
        out = list(exponential(base, multiplier, limit)())
        self.assertEqual([], out)

    def test_valid(self):
        base, multiplier, limit = 2, 3, 2
        out = list(exponential(base, multiplier, limit)())
        self.assertEqual([3, 6], out)


class TestFibonacci(unittest.TestCase):

    def test_negative_multiplier(self):
        multiplier, limit = -1, 1
        with self.assertRaises(ValueError):
            list(fibonacci(multiplier, limit)())

    def test_zero_multiplier(self):
        multiplier, limit = 0, 1
        out = list(fibonacci(multiplier, limit)())
        self.assertEqual([0], out)

    def test_negative_limit(self):
        multiplier, limit = 1, -1
        with self.assertRaises(ValueError):
            list(fibonacci(multiplier, limit)())

    def test_zero_limit(self):
        multiplier, limit = 1, 0
        out = list(fibonacci(multiplier, limit)())
        self.assertEqual([], out)

    def test_valid(self):
        multiplier, limit = 10, 3
        out = list(fibonacci(multiplier, limit)())
        self.assertEqual([10, 10, 20], out)


if __name__ == '__main__':
    unittest.main()

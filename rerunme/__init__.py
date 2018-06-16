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

"""Function decorator for retrying function for a given return value or raised exception with delays.

This exports:
  - rerunme is the function retry decorator
  - MaxRetryError is an exception raised for exceeding the maximum retries
  - constant is a delay generator for constant delays
  - linear is a delay generator for linearly increasing delays
  - exponential is a delay generator for exponentially increasing delays
  - fibonacci is a delay generator for fibonacci delays
"""

from inspect import signature, Parameter
from functools import wraps
from time import sleep


class MaxRetryError(Exception):
    """Maximum retries have been exceeded."""
    pass


class _FunctionSignature:
    """Flags for parameters accepted by function signature."""
    NORMAL = 1 << 0
    ARGS = 1 << 1
    KWARGS = 1 << 2


class rerunme:
    """Retry decorator.

        Wraps a function and retries it depending on the return value or an exception that is raised. Different
        algorithms can be used to implement varying delays after each retry. See `constant`, `linear`, `exponential`,
        and `fibonacci`.

        Each of the functions that can be passed in (`on_delay`, `on_error`, `on_return`, and `on_retry`) can
        either accept 0 parameters, the number of parameters as described below, or the wrapped function's args and
        kwargs in addition to the parameters as described below.

        For usage examples, see https://github.com/jaredlgillespie/rerunme.

        :param on_delay:
            If iterable or callable function, should generate the time delays between successive retries. Each iteration
            should yield an integer value representing the time delay in milliseconds. The iterable should ideally have
            an internal limit in which to stop, see :func:`exponential` for an example.

            If an integer or float, should represent a single delay in milliseconds.

            If None type, no retries are performed.
        :param on_error:
            If a callable, should accept a single value (the error) which is raised and return a boolean value. True
            denotes that the error should be handled and the function retried, while False allows it to bubble up
            without continuing to retry the function.

            If an iterable, should be a sequence of Exception types that can be handled. Exceptions that are not one of
            these types cause the error to bubble up without continuing to retry the function.

            If an Exception type, an exception that occurs of this type is handled. All others are bubbled up without
            continuing to retry the function.

            If None type, no errors are handled.
        :param on_return:
            If a callable, should accept a single value (the return value) which is return and return a boolean value.
            True denotes that the return value should result in the function being retried, while False allows the
            return value to be returned from the function.

            If an iterable, should be a sequence of values that can be handled (i.e. the function is retried). Values
            that are not equal to one of these are returned from the function.

            If a single value, a return values that occurs that is equal is handled. All others are returned from the
            function.

            If None type, no return values are handled. Note that if the None type is actually desired to be handled, it
            should be given as a sequence like so: `on_return=[None]`.
        :param on_retry:
            A callback that is called each time the function is retried. Two arguments are passed, the current delay and
            the number of retries thus far.
        :param retry_after_delay:
            A boolean value indicating whether to call the `on_retry` callback before or after the delay is issued.
            True indicates after, while False indicates before.
        :type on_delay: iterable or callable or int or float or None
        :type on_error: iterable or callable or Exception or None
        :type on_return: iterable or callable or object or None
        :type on_retry: callable or None
        :type retry_after_delay: bool
        :raises MaxRetryException:
            If number of retries has been exceeded, determined by `on_delay` generator running.
        """
    def __init__(self, on_delay=None, on_error=None, on_return=None, on_retry=None, retry_after_delay=False):
        self._on_delay = on_delay
        self._on_error = on_error
        self._on_return = on_return
        self._on_retry = on_retry
        self._retry_after_delay = retry_after_delay

        # Signatures
        self._sig_delay = None if not callable(on_delay) else self._define_function_signature(on_delay)
        self._sig_error = None if not self._error_is_callable() else self._define_function_signature(on_error)
        self._sig_return = None if not callable(on_return) else self._define_function_signature(on_return)
        self._sig_retry = None if not callable(on_retry) else self._define_function_signature(on_retry)

    def __call__(self, func):
        @wraps(func)
        def func_wrapper(*args, **kwargs):
            return self.run(func, *args, **kwargs)

        return func_wrapper

    def run(self, func, *args, **kwargs):
        """Executes a function using this as the wrapper.

        :param func:
            A function to wrap and call.
        :param args:
            Arguments to pass to the function.
        :param kwargs:
            Keyword arguments to pass to the function.
        :type func: function
        """
        try:
            ret = func(*args, **kwargs)

            if not self._should_handle_return(ret, *args, **kwargs):
                return ret
        except Exception as e:
            if not self._should_handle_error(e, *args, **kwargs):
                raise

        if self._on_delay is None:
            raise MaxRetryError('Maximum number of retries exceeded for {0}'.format(self._get_func_name(func)))

        retries = 0
        for delay in self._get_delay_sequence(*args, **kwargs):
            retries += 1

            if self._should_handle_retry(False):
                self._on_retry(delay, retries)

            sleep(delay / 1000)

            if self._should_handle_retry(True):
                self._on_retry(delay, retries)

            try:
                ret = func(*args, **kwargs)

                if not self._should_handle_return(ret, *args, **kwargs):
                    return ret
            except Exception as e:
                if not self._should_handle_error(e, *args, **kwargs):
                    raise

        raise MaxRetryError('Maximum number of retries exceeded for {0}'.format(self._get_func_name(func)))

    def _call_with_sig(self, func, sig, internal_args, *args, **kwargs):
        if not sig:
            return func()
        elif sig & (_FunctionSignature.ARGS | _FunctionSignature.KWARGS):
            return func(*(internal_args + args), **kwargs)
        else:
            return func(*internal_args)

    def _define_function_signature(self, func):
        sig = None

        for param in signature(func).parameters.values():
            if param.kind == Parameter.POSITIONAL_OR_KEYWORD:
                sig = (sig or _FunctionSignature.NORMAL) | _FunctionSignature.NORMAL
            elif param.kind == Parameter.VAR_KEYWORD:
                sig = (sig or _FunctionSignature.KWARGS) | _FunctionSignature.KWARGS
            elif param.kind == Parameter.VAR_POSITIONAL:
                sig = (sig or _FunctionSignature.ARGS) | _FunctionSignature.ARGS

        return sig

    def _error_is_callable(self):
        return callable(self._on_error) and \
                       (not isinstance(self._on_error, type) or not issubclass(self._on_error, Exception))

    def _get_delay_sequence(self, *args, **kwargs):
        if callable(self._on_delay):
            return self._call_with_sig(self._on_delay, self._sig_delay, (), *args, **kwargs)
        elif self._is_iterable(self._on_delay):
            return self._on_delay
        return [self._on_delay]

    def _get_func_name(self, func):
        if hasattr(func, '__name__'):
            return func.__name__
        else:
            # Partials are nameless, so grab the variable from the local symbol table
            return [k for k, v in locals().items() if v == func][0]

    def _is_iterable(self, obj):
        try:
            iter(obj)
            return True
        except TypeError:
            return False

    def _should_handle_error(self, error, *args, **kwargs):
        if self._on_error is not None:
            # Callables are OK, but not if an Exception is given, we have to make sure we don't
            # call `issubclass` with a non-class object
            if self._error_is_callable():
                return self._call_with_sig(self._on_error, self._sig_error, (error,), *args, **kwargs)
            elif self._is_iterable(self._on_error):
                return isinstance(error, tuple(self._on_error))
            else:
                return isinstance(error, self._on_error)
        return False

    def _should_handle_return(self, value, *args, **kwargs):
        if self._on_return is not None:
            if callable(self._on_return):
                return self._call_with_sig(self._on_return, self._sig_return, (value,), *args, **kwargs)
            elif self._is_iterable(self._on_return):
                return value in self._on_return
            else:
                return value == self._on_return
        return False

    def _should_handle_retry(self, after_delay):
        if self._on_retry is not None:
            return self._retry_after_delay == after_delay
        return False


def constant(delay, limit):
    """Constant delay generator.

    :param delay:
        The delay in milliseconds.
    :param limit:
        The number of delays to yield.
    :type delay: int or float
    :type limit: int
    :return:
        A generator function which yields a sequence of delays.
    :rtype: function
    """
    def func():
        if delay < 0:
            raise ValueError('delay must be non-negative')

        if limit < 0:
            raise ValueError('limit must be non-negative')

        for _ in range(limit):
            yield delay

    return func


def linear(start, increment, limit):
    """Linear delay generator.

    Creates a function generator that yields a constant delay at each iteration.

    :param start:
        The starting delay in milliseconds.
    :param increment:
        The amount to increment the delay after each iteration.
    :param limit:
        The number of delays to yield.
    :type start: int or float
    :type increment: int or float
    :type limit: int
    :return:
        A generator function which yields a sequence of delays.
    :rtype: function
    """
    def func():
        if start < 0:
            raise ValueError('start must be non-negative')

        if limit < 0:
            raise ValueError('limit must be non-negative')

        if increment < 0 and start + increment * limit < 0:
            raise ValueError('parameters will yield negative result')

        delay = start
        for _ in range(limit):
            yield delay
            delay += increment

    return func


def exponential(base, multiplier, limit):
    """Exponential delay generator.

    Creates a function generator that yields an exponentially increasing delay at each iteration.

    :param base:
        The base to raise to a power.
    :param multiplier:
        The amount to multiply the delay by for each iteration.
    :param limit:
        The number of delays to yield.
    :type base: int or float
    :type multiplier: int or float
    :type limit: int
    :return:
        A generator function which yields a sequence of delays.
    :rtype: function
    """
    def func():
        if base < 0:
            raise ValueError('base must be non-negative')

        if multiplier < 0:
            raise ValueError('multiplier must be non-negative')

        if limit < 0:
            raise ValueError('limit must be non-negative')

        delay = base
        for exp in range(limit):
            yield delay**exp * multiplier

    return func


def fibonacci(multiplier, limit):
    """Fibonacci delay generator.

    Creates a function generator that yields a fibonacci delay sequence.

    :param multiplier:
        The amount to multiply the delay by for each iteration.
    :param limit:
        The number of delays to yield.
    :type multiplier: int or float
    :type limit: int
    :return:
        A generator function which yields a sequence of delays.
    :rtype: function
    """
    def func():
        if multiplier < 0:
            raise ValueError('multiplier must be non-negative')

        if limit < 0:
            raise ValueError('limit must be non-negative')

        a, b = 0, 1
        for _ in range(limit):
            a, b = b, a + b
            yield a * multiplier

    return func

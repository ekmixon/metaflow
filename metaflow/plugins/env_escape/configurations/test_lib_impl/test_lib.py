import functools


class MyBaseException(Exception):
    pass


class SomeException(MyBaseException):
    pass


class TestClass1(object):

    cls_object = 25

    def __init__(self, value):
        self._value = value
        self._value2 = 123

    def unsupported_method(self):
        pass

    def print_value(self):
        return self._value

    def __str__(self):
        return f"My str representation is {str(self._value)}"

    def __repr__(self):
        return f"My repr representation is {str(self._value)}"

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value

    def to_class2(self, count, stride=1):
        return TestClass2(self._value, stride, count)

    @staticmethod
    def somethingstatic(val):
        return val + 42

    @classmethod
    def somethingclass(cls):
        return cls.cls_object

    @property
    def override_value(self):
        return self._value2

    @override_value.setter
    def override_value(self, value):
        self._value2 = value


class TestClass2(object):
    def __init__(self, value, stride, count):
        self._mylist = [value + stride * i for i in range(count)]

    def something(self, val):
        return f"In Test2 with {val}"

    def __iter__(self):
        self._pos = 0
        return self

    def __next__(self):
        if self._pos < len(self._mylist):
            self._pos += 1
            return self._mylist[self._pos - 1]
        raise StopIteration


class TestClass3(object):
    def __init__(self):
        print("I am Class3")

    def thirdfunction(self, val):
        print(f"Got value: {val}")
        # raise AttributeError("Some weird error")

    def raiseSomething(self):
        raise SomeException("Something went wrong")

    def __hidden(self, name, value):
        setattr(self, name, value)

    def weird_indirection(self, name):
        return functools.partial(self.__hidden, name)


def test_func(*args, **kwargs):
    return "In test func"


test_value = 1

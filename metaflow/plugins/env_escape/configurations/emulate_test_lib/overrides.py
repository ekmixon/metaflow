from metaflow.plugins.env_escape.override_decorators import (
    local_override,
    local_getattr_override,
    local_setattr_override,
    remote_override,
    remote_getattr_override,
    remote_setattr_override,
    local_exception,
    remote_exception_serialize,
)


@local_override({"test_lib.TestClass1": "print_value"})
def local_print_value(stub, func):
    print("Encoding before sending to server")
    v = func()
    print("Adding 5")
    return v + 5


@remote_override({"test_lib.TestClass1": "print_value"})
def remote_print_value(obj, func):
    print("Decoding from client")
    v = func()
    print("Encoding for client")
    return v

@local_getattr_override({"test_lib.TestClass1": "override_value"})
def local_get_value2(stub, name, func):
    print(f"In local getattr override for {name}")
    r = func()
    print(f"In local getattr override, got {r}")
    return r


@local_setattr_override({"test_lib.TestClass1": "override_value"})
def local_set_value2(stub, name, func, v):
    print(f"In local setattr override for {name}")
    r = func(v)
    print(f"In local setattr override, got {r}")
    return r


@remote_getattr_override({"test_lib.TestClass1": "override_value"})
def remote_get_value2(obj, name):
    print(f"In remote getattr override for {name}")
    r = getattr(obj, name)
    print(f"In remote getattr override, got {r}")
    return r


@remote_setattr_override({"test_lib.TestClass1": "override_value"})
def remote_set_value2(obj, name, v):
    print(f"In remote setattr override for {name}")
    r = setattr(obj, name, v)
    print(f"In remote setattr override, got {r}")
    return r


@local_override({"test_lib.TestClass1": "unsupported_method"})
def unsupported_method(stub, func, *args, **kwargs):
    return NotImplementedError("Just because")


@local_override({"test_lib.package.TestClass3": "thirdfunction"})
def iamthelocalthird(stub, func, val):
    print("Locally the Third")
    return func(val)


@remote_override({"test_lib.package.TestClass3": "thirdfunction"})
def iamtheremotethird(obj, func, val):
    print("Remotely the Third")
    return func(val)


@local_exception("test_lib.SomeException")
class SomeException:
    def __str__(self):
        parent_val = super(self.__realclass__, self).__str__()
        return parent_val + f" In SomeException str override: {self.user_value}"

    def _deserialize_user(self, json_obj):
        self.user_value = json_obj

@remote_exception_serialize("test_lib.SomeException")
def some_exception_serialize(ex):
    return 42

from __future__ import annotations

import enum
from typing import (
    Dict,
    Type,
    Tuple,
    Union,
    NoReturn,
    Iterable,
    List,
    TypeVar,
    Generic,
    Any,
    TYPE_CHECKING,
    Optional,
)

from .context import context, property_type
from .context import get_boolean
from .context import get_number
from .context import get_object
from .context import get_text
from .context import object_name
from .context import property_constant_name
from .context import property_constant_number
from .context import property_name
from .context import query_type
from .context import set_boolean
from .context import set_number
from .context import set_object
from .context import set_text
from .generic_object import BaseObject, ValueTypes, GenericObject
from .property_types import Properties

if TYPE_CHECKING:  # pragma: no cover
    from . import Module

registered_objects: Dict[str, Union[Type[GenericObject], Type["Module"]]] = {}


class ObjectProperties(enum.Enum):
    canvases = "D2FP_CANVAS"
    alerts = "D2FP_ALERT"
    attached_libraries = "D2FP_ATT_LIB"
    data_blocks = "D2FP_BLOCK"
    form_parameters = "D2FP_FORM_PARAM"
    graphics = "D2FP_GRAPHIC"
    items = "D2FP_ITEM"
    points = "D2FP_POINT"
    program_units = "D2FP_PROG_UNIT"
    property_classes = "D2FP_PROP_CLASS"
    radio_buttons = "D2FP_RADIO_BUTTON"
    relations = "D2FP_RELATION"
    tab_pages = "D2FP_TAB_PAGE"
    triggers = "D2FP_TRIGGER"
    visual_attributes = "D2FP_VIS_ATTR"
    windows = "D2FP_WINDOW"
    data_source_arguments = "D2FP_DAT_SRC_ARG"
    data_source_columns = "D2FP_DAT_SRC_COL"
    editors = "D2FP_EDITOR"
    event = "D2FP_EVENT"
    lovs = "D2FP_LOV"
    lov_column_maps = "D2FP_LV_COLMAP"
    menus = "D2FP_MENU"
    menu_items = "D2FP_MENU_ITEM"
    object_groups = "D2FP_OBJ_GRP"
    object_children = "D2FP_OBG_CHILD"
    record_groups = "D2FP_REC_GRP"
    record_group_colspecs = "D2FP_COL_SPEC"
    reports = "D2FP_REPORT"
    column_value = "D2FP_COLUMN_VALUE"


class Common:
    def __init__(self, constant: str):
        self.constant = constant


class Unknown(Common):
    def __get__(self, instance: BaseObject, owner: Type[BaseObject]) -> None:
        return None

    def __set__(self, instance: BaseObject, value: None) -> NoReturn:
        raise NotImplementedError()


class Text(Common):
    def __get__(self, instance: BaseObject, owner: Type[BaseObject]) -> str:
        return (
            get_text(instance, property_constant_number(self.constant)) or b""
        ).decode(context.encoding)

    def __set__(self, instance: BaseObject, value: str) -> None:
        set_text(
            instance,
            property_constant_number(self.constant),
            value.encode(context.encoding),
        )


U = TypeVar("U")


class BasicAttribute(Common, Generic[U]):
    @staticmethod
    def _getter(instance: BaseObject, property_constant: int) -> U:
        raise NotImplementedError()  # pragma: no cover

    @staticmethod
    def _setter(instance: BaseObject, property_constant: int, value: U) -> U:
        raise NotImplementedError()  # pragma: no cover

    def __get__(self, instance: BaseObject, owner: Type[BaseObject]) -> U:
        return self._getter(instance, property_constant_number(self.constant))

    def __set__(self, instance: BaseObject, value: U) -> None:
        self._setter(instance, property_constant_number(self.constant), value)


class Bool(BasicAttribute[bool]):
    _getter = staticmethod(get_boolean)  # type: ignore
    _setter = staticmethod(set_boolean)  # type: ignore


class Number(BasicAttribute[int]):
    _getter = staticmethod(get_number)  # type: ignore
    _setter = staticmethod(set_number)  # type: ignore


T = TypeVar("T")


class Object(Common, Generic[T]):
    def __get__(
        self, instance: BaseObject, owner: Type[BaseObject]
    ) -> Optional[BaseObject]:
        obj = get_object(instance, property_constant_number(self.constant))
        if obj:
            klass = get_object_constructor(obj)
            return klass(obj)
        return None

    def __set__(self, instance: BaseObject, value: BaseObject) -> None:
        set_object(instance, property_constant_number(self.constant), value)


properties = {
    ValueTypes.UNKNOWN: Unknown,
    ValueTypes.BOOLEAN: Bool,
    ValueTypes.NUMBER: Number,
    ValueTypes.TEXT: Text,
    ValueTypes.OBJECT: Object,
}


def get_object_constructor(obj: BaseObject) -> Union[Type[Module], Type[GenericObject]]:
    obj_name = object_name(query_type(obj))
    klass = registered_objects.get(obj_name, GenericObject)
    return klass


class Subobjects(Generic[T]):
    def __init__(self, constant: str) -> None:
        self.constant = constant

    # todo: this generates a new list every time would be better if its the same list, then
    #  could operate on that list object creation/deletion and you won't have multiple inconsistent lists
    def __get__(
        self, instance: GenericObject, owner: Type[GenericObject]
    ) -> List[BaseObject]:
        def gen_subobjects() -> Iterable[BaseObject]:
            first_child = get_object(instance, property_constant_number(self.constant))
            if first_child:
                klass = get_object_constructor(first_child)

                child = klass(first_child)
                while child:
                    yield child
                    child = klass(child.next_object)  # type: ignore

        subobjects = list(gen_subobjects())
        return subobjects

    def __set__(self, instance: BaseObject, value: List[BaseObject]) -> NoReturn:
        raise AttributeError("can't set attribute")


# todo: kinda redundant since i have property_types.Properties
def property_attribute(
    property_number: int,
) -> Tuple[str, Union[Common, Subobjects[BaseObject]]]:
    constant_name = property_constant_name(property_number)
    const_name = f"D2FP_{constant_name}"
    try:
        obj_property = ObjectProperties(const_name)
    except ValueError:
        prop_name = (
            "_".join(property_name(property_number).lower().split())
            .replace("'", "")
            .replace("-", "_")
            .replace("/", "_")
        )
        value_type = ValueTypes(property_type(property_number=property_number))
        klass = properties[value_type]
        return prop_name, klass(constant_name)
    else:
        prop_name = obj_property.name
        return prop_name, Subobjects(property_constant_name(property_number))


def object_type(cls: Type[BaseObject], api_objects: Dict) -> Tuple[Dict, int]:  # type: ignore
    try:
        obj_type = api_objects[cls.object_type.value]
    except KeyError:
        # todo: clean up dirty hack
        #  mostly for column_value, which seems to be not documented by orcl anyway
        #  other objects also do not have their own specific entries
        obj_type = api_objects["D2FFO_ANY"]
        object_number = 6
    else:
        object_number = obj_type["object_number"]

    return obj_type, object_number


def add_properties(klass: Type[BaseObject], api_objects: Dict) -> Type[BaseObject]:  # type: ignore
    obj_type, klass._object_number = object_type(klass, api_objects)

    # todo: at this point, forms should be initialized, should be able to dynamically
    #  add properties..?
    for forms_object_property in obj_type["properties"]:

        property_number = forms_object_property["property_number"]

        attribute: Union[str, Union[Common, Subobjects[BaseObject]]]
        # todo: probably do not even need this function call anymore...
        prop_name, attribute = property_attribute(property_number)

        if prop_name and "(obsolete)" not in prop_name:
            try:
                prop_name = Properties(property_number).name.rstrip("_")
            except ValueError:  # pragma: no cover
                raise RuntimeError(f"Unrecognized property ({prop_name})")

            if prop_name in dir(klass):
                continue
            setattr(klass, prop_name, attribute)

    return klass


def forms_object(
    klass: Union[Type[Module], Type[GenericObject]]
) -> Union[Type[Module], Type[GenericObject]]:
    registered_objects[klass.object_type.value[6:]] = klass
    return klass

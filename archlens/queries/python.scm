;; Decorated classes
(class_definition
  (decorator (identifier) @decorator.name)
  name: (identifier) @class.name) @class.def

(class_definition
  (decorator
    (call
      function: (attribute
        object: (identifier) @decorator.obj
        attribute: (identifier) @decorator.attr)))
  name: (identifier) @class.name) @class.def_attr

;; Plain class with inheritance
(class_definition
  name: (identifier) @class.name
  superclasses: (argument_list (identifier) @class.extends)?) @class.plain

;; Decorated functions (FastAPI / Flask routes)
(decorated_definition
  (decorator
    (call
      function: (attribute
        object: (identifier) @route.obj
        attribute: (identifier) @route.method)))
  definition: (function_definition name: (identifier) @func.name)) @route.def

(decorated_definition
  (decorator (identifier) @decorator.name)
  definition: (function_definition name: (identifier) @func.name)) @func.decorated

;; Plain function definitions
(function_definition
  name: (identifier) @func.name) @func.plain

;; Import statements
(import_from_statement
  module_name: (dotted_name) @import.module
  name: (dotted_name) @import.name)

(import_from_statement
  module_name: (dotted_name) @import.module
  name: (aliased_import name: (dotted_name) @import.name))

(import_statement
  name: (dotted_name) @import.module)

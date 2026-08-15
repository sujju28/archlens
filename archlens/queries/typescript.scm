;; Decorated class declarations (NestJS / Angular)
(class_declaration
  decorator: (decorator
    [(call_expression function: (identifier) @decorator.name)
     (identifier) @decorator.name])
  name: (type_identifier) @class.name) @class.def

;; Plain class declarations
(class_declaration
  name: (type_identifier) @class.name) @class.plain

;; Class extends React.Component
(class_declaration
  name: (type_identifier) @class.name
  (class_heritage (extends_clause (member_expression) @class.extends))) @react.class

;; Exported function (potential React FC)
(export_statement
  declaration: (function_declaration
    name: (identifier) @func.name) @func.def)

;; Arrow function components assigned to const
(export_statement
  declaration: (lexical_declaration
    (variable_declarator
      name: (identifier) @func.name
      value: (arrow_function) @func.arrow))) @func.const

;; Import statements
(import_statement
  source: (string) @import.source
  (import_clause (identifier) @import.default)?)

(import_statement
  source: (string) @import.source
  (import_clause (named_imports (import_specifier name: (identifier) @import.name))))

;; JSX element usage (composition)
(jsx_element
  open_tag: (jsx_opening_element name: (identifier) @jsx.component))

(jsx_self_closing_element
  name: (identifier) @jsx.component)

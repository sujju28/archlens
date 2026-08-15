;; Match annotated class declarations
(class_declaration
  (modifiers
    [(marker_annotation name: (identifier) @annotation.name)
     (annotation name: (identifier) @annotation.name
       arguments: (annotation_argument_list)? @annotation.args)])
  name: (identifier) @class.name
  superclass: (superclass (type_identifier) @class.extends)?
  interfaces: (super_interfaces (type_list (type_identifier) @class.implements))?) @class.def

;; Unannotated class declarations (fallback)
(class_declaration
  name: (identifier) @class.name
  superclass: (superclass (type_identifier) @class.extends)?
  interfaces: (super_interfaces (type_list (type_identifier) @class.implements))?) @class.plain

;; Match field injections
(field_declaration
  (modifiers (marker_annotation name: (identifier) @field.annotation))
  type: (type_identifier) @field.type
  declarator: (variable_declarator name: (identifier) @field.name)) @field.def

;; Match method-level annotations (e..g., @GetMapping)
(method_declaration
  (modifiers
    [(marker_annotation name: (identifier) @method.annotation)
     (annotation name: (identifier) @method.annotation
       arguments: (annotation_argument_list)? @method.annotation.args)])
  name: (identifier) @method.name) @method.def

;; Package declaration
(package_declaration (scoped_identifier) @package.name)
(package_declaration (identifier) @package.name)

;; Import declarations
(import_declaration (scoped_identifier) @import.name)
(import_declaration (identifier) @import.name)

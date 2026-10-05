// This utility extracts exact upstream method bytes; it does not reimplement Schema.
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"strconv"
	"strings"
)

func main() {
	if len(os.Args) != 3 {
		panic("usage: extract SOURCE OUTPUT")
	}
	source, e := os.ReadFile(os.Args[1])
	if e != nil {
		panic(e)
	}
	fset := token.NewFileSet()
	file, e := parser.ParseFile(fset, os.Args[1], source, 0)
	if e != nil {
		panic(e)
	}
	var method *ast.FuncDecl
	for _, d := range file.Decls {
		if f, ok := d.(*ast.FuncDecl); ok && f.Name.Name == "Schema" && f.Recv != nil {
			if method != nil {
				panic("ambiguous Schema")
			}
			method = f
		}
	}
	if method == nil {
		panic("Schema absent")
	}
	uses := map[string]bool{}
	ast.Inspect(method, func(n ast.Node) bool {
		if s, ok := n.(*ast.SelectorExpr); ok {
			if id, ok := s.X.(*ast.Ident); ok {
				uses[id.Name] = true
			}
		}
		return true
	})
	if uses["r"] {
		panic("Schema depends on receiver state")
	}
	out := "// AST-extracted upstream Schema with minimal inert receiver. Not full provider resource.\npackage contract\nimport (\n"
	for _, i := range file.Imports {
		p, _ := strconv.Unquote(i.Path.Value)
		parts := strings.Split(p, "/")
		name := parts[len(parts)-1]
		if i.Name != nil {
			name = i.Name.Name
		}
		if uses[name] {
			if i.Name != nil {
				out += name + " "
			}
			out += i.Path.Value + "\n"
		}
	}
	out += ")\ntype SettingsCatalogJsonResource struct{}\n"
	start, end := fset.Position(method.Pos()).Offset, fset.Position(method.End()).Offset
	body := source[start:end]
	out += string(body) + "\n"
	if e = os.WriteFile(os.Args[2], []byte(out), 0600); e != nil {
		panic(e)
	}
	hash := sha256.Sum256(body)
	sourceHash := sha256.Sum256(source)
	result := map[string]any{"method_sha256": hex.EncodeToString(hash[:]), "source_sha256": hex.EncodeToString(sourceHash[:]), "start_byte": start, "end_byte_exclusive": end, "start_line": fset.Position(method.Pos()).Line, "end_line": fset.Position(method.End()).Line, "receiver": "minimal inert struct; lifecycle absent", "qualification": "AST-extracted Schema only"}
	data, _ := json.Marshal(result)
	fmt.Println(string(data))
}

package recipe

import (
	"bytes"
	"errors"
	"fmt"
	"io"
	"os"
	"strings"

	"gopkg.in/yaml.v3"
)

const APIVersion = "agenyx.ai/v1alpha1"

type Metadata struct {
	Name    string `yaml:"name"`
	Version string `yaml:"version,omitempty"`
}

// Document is the common envelope shared by every Agenyx recipe kind.
// Spec is decoded into a component-specific type by the consumer.
type Document struct {
	APIVersion string      `yaml:"apiVersion"`
	Kind       string      `yaml:"kind"`
	Metadata   Metadata    `yaml:"metadata"`
	Spec       yaml.Node   `yaml:"spec"`
}

func LoadFile(path string) (*Document, error) {
	if strings.TrimSpace(path) == "" {
		return nil, errors.New("recipe path must not be empty")
	}

	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open recipe %q: %w", path, err)
	}
	defer file.Close()

	decoder := yaml.NewDecoder(file)
	decoder.KnownFields(true)

	var doc Document
	if err := decoder.Decode(&doc); err != nil {
		return nil, fmt.Errorf("decode recipe %q: %w", path, err)
	}

	// A recipe file must contain exactly one YAML document.
	var extra yaml.Node
	if err := decoder.Decode(&extra); err != io.EOF {
		if err == nil {
			return nil, fmt.Errorf("decode recipe %q: multiple YAML documents are not allowed", path)
		}
		return nil, fmt.Errorf("decode recipe %q: %w", path, err)
	}

	if err := doc.Validate(); err != nil {
		return nil, fmt.Errorf("validate recipe %q: %w", path, err)
	}

	return &doc, nil
}

func (d *Document) Validate() error {
	if d.APIVersion != APIVersion {
		return fmt.Errorf(
			"unsupported apiVersion %q; expected %q",
			d.APIVersion,
			APIVersion,
		)
	}

	if strings.TrimSpace(d.Kind) == "" {
		return errors.New("kind must not be empty")
	}

	if strings.TrimSpace(d.Metadata.Name) == "" {
		return errors.New("metadata.name must not be empty")
	}

	if d.Spec.Kind != yaml.MappingNode {
		return errors.New("spec must be a YAML mapping")
	}

	return nil
}

// DecodeSpec decodes the component-specific spec and rejects unknown fields.
// Consumers should validate the decoded values after calling this method.
func (d *Document) DecodeSpec(dst any) error {
	if d == nil {
		return errors.New("recipe document must not be nil")
	}
	if dst == nil {
		return errors.New("recipe spec destination must not be nil")
	}

	data, err := yaml.Marshal(&d.Spec)
	if err != nil {
		return fmt.Errorf("encode recipe spec: %w", err)
	}

	decoder := yaml.NewDecoder(bytes.NewReader(data))
	decoder.KnownFields(true)

	if err := decoder.Decode(dst); err != nil {
		return fmt.Errorf("decode recipe spec: %w", err)
	}

	return nil
}

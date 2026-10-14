package domain

type SandboxSpec struct {
	ResourceLimits   ResourceLimits
	FilesystemPolicy FilesystemPolicy
	NetworkPolicy    NetworkPolicy
}

func (s SandboxSpec) Validate() error {
	if err := s.ResourceLimits.Validate(); err != nil {
		return err
	}

	if err := s.FilesystemPolicy.Validate(); err != nil {
		return err
	}

	if err := s.NetworkPolicy.Validate(); err != nil {
		return err
	}

	return nil
}

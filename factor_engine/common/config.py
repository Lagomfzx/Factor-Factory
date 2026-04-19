import os


class FactoryConfig:
    """Factory-wide path configuration."""

    def __init__(self, factory_name: str, version: str, base_dir: str = "mydata/output"):
        self.factory_name = factory_name
        self.version = version
        self.base_dir = base_dir

        self.llm_output_dir = os.path.join(self.base_dir, "llm_output", f"llm_output_{self.version}")
        self.combined_output_dir = os.path.join(self.base_dir, "llm_output", f"combined_{self.version}")
        self.factor_out_dir = os.path.join(self.base_dir, "factor", f"日频因子_{self.version}")
        self.remote_result_dir = os.path.join(self.base_dir, "remote_json")

        self.registry_csv = os.path.join(self.base_dir, "job_id_output", f"job_id_output_{self.version}.csv")
        self.premium_registry_csv = os.path.join(
            self.base_dir,
            "job_id_output",
            f"job_id_output_{self.version}.1.csv",
        )

        opt_dir = os.path.join(self.base_dir, "opt_data", f"{self.factory_name}_{self.version}")
        self.history_file = os.path.join(self.llm_output_dir, "factor_gpt_history.txt")
        self.db_path = os.path.join(
            self.base_dir,
            "cache",
            f"factor_hashes_{self.factory_name}_{self.version}.db",
        )
        self.evolution_history_csv = os.path.join(opt_dir, f"factor_evolution_history_{self.version}.csv")
        self.research_notes_csv = os.path.join(opt_dir, f"research_notes_{self.version}.csv")
        self.referee_notes_csv = os.path.join(opt_dir, f"research_referee_notes_{self.version}.csv")
        self.tags_registry_csv = os.path.join(opt_dir, f"factor_tags_registry_{self.version}.csv")

        self._make_dirs()

    def _make_dirs(self):
        for path in [self.llm_output_dir, self.combined_output_dir, self.factor_out_dir, self.remote_result_dir]:
            os.makedirs(path, exist_ok=True)

        for file_path in [
            self.registry_csv,
            self.premium_registry_csv,
            self.evolution_history_csv,
            self.research_notes_csv,
            self.referee_notes_csv,
            self.tags_registry_csv,
            self.db_path,
        ]:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

        print(f"[{self.factory_name.upper()} Factory] Path config ready (version={self.version})")

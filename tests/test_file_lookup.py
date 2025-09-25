from datetime import datetime, timedelta

import pytest

from mlglobal.ic_downloader import FileLookup


class TestFileLookup:
    """Test cases for the FileLookup class."""

    def test_init_gfs(self):
        """Test FileLookup initialization for GFS mode."""
        current_cycle = datetime(2023, 1, 1, 12, 0, 0)
        lookup = FileLookup(current_cycle, num_levels=13, member=None)

        assert lookup.current_cycle == current_cycle
        assert lookup.num_levels == 13
        assert lookup.member is None
        assert lookup.current_cycle_m6h == current_cycle - timedelta(hours=6)
        assert lookup.get_file_info == lookup._gfs_file_info

    def test_init_gefs(self):
        """Test FileLookup initialization for GEFS mode."""
        current_cycle = datetime(2023, 1, 1, 12, 0, 0)
        lookup = FileLookup(current_cycle, num_levels=13, member="c00")

        assert lookup.current_cycle == current_cycle
        assert lookup.num_levels == 13
        assert lookup.member == "c00"
        assert lookup.current_cycle_m6h == current_cycle - timedelta(hours=6)
        assert lookup.get_file_info == lookup._gefs_file_info

    def test_gfs_file_info_13_levels(self):
        """Test GFS file info generation for 13 levels."""
        current_cycle = datetime(2023, 1, 1, 12, 0, 0)
        lookup = FileLookup(current_cycle, num_levels=13, member=None)

        file_dict = lookup._gfs_file_info()

        # Check structure
        assert len(file_dict) == 2
        assert current_cycle in file_dict
        assert lookup.current_cycle_m6h in file_dict

        # Check current cycle files
        current_files = file_dict[current_cycle]
        assert len(current_files) == 2
        assert "gfs.20230101/12/atmos/gfs.t12z.pgrb2.0p25.f000" in current_files[0]
        assert "gfs.20230101/06/atmos/gfs.t06z.pgrb2.0p25.f006" in current_files[1]

        # Check previous cycle files
        prev_files = file_dict[lookup.current_cycle_m6h]
        assert len(prev_files) == 1
        assert "gfs.20230101/06/atmos/gfs.t06z.pgrb2.0p25.f000" in prev_files[0]

    def test_gfs_file_info_37_levels(self):
        """Test GFS file info generation for 37 levels."""
        current_cycle = datetime(2023, 1, 1, 12, 0, 0)
        lookup = FileLookup(current_cycle, num_levels=37, member=None)

        file_dict = lookup._gfs_file_info()

        # Check current cycle has additional pgrb2b file
        current_files = file_dict[current_cycle]
        assert len(current_files) == 3
        assert any("pgrb2b.0p25" in f for f in current_files)

    def test_gefs_file_info(self):
        """Test GEFS file info generation."""
        current_cycle = datetime(2023, 1, 1, 12, 0, 0)
        lookup = FileLookup(current_cycle, num_levels=13, member="c00")

        file_dict = lookup._gefs_file_info()

        # Check structure
        assert len(file_dict) == 2
        assert current_cycle in file_dict
        assert lookup.current_cycle_m6h in file_dict

        # Check current cycle files
        current_files = file_dict[current_cycle]
        assert len(current_files) == 2
        assert "gec00.t12z.pgrb2.0p25.f000" in current_files[0]
        assert "gec00.t12z.pgrb2s.0p25.f000" in current_files[1]

        # Check previous cycle files
        prev_files = file_dict[lookup.current_cycle_m6h]
        assert len(prev_files) == 2
        assert "gec00.t06z.pgrb2.0p25.f000" in prev_files[0]
        assert "gec00.t06z.pgrb2s.0p25.f000" in prev_files[1]

    @pytest.mark.parametrize("num_levels,expected_current_files", [
        (13, 2),  # For 13 levels: pgrb2.0p25 files only
        (37, 3),  # For 37 levels: includes pgrb2b.0p25 file
    ])
    def test_gfs_file_count_by_levels(self, num_levels, expected_current_files):
        """Test that GFS mode generates correct number of files based on levels."""
        current_cycle = datetime(2023, 1, 1, 12, 0, 0)
        lookup = FileLookup(current_cycle, num_levels=num_levels, member=None)
        file_dict = lookup._gfs_file_info()

        # Check current cycle files
        current_files = file_dict[current_cycle]
        assert len(current_files) == expected_current_files

    @pytest.mark.parametrize("member", ["c00", "p01", "p15", "p30"])
    def test_gefs_members(self, member):
        """Test GEFS mode with different member values."""
        current_cycle = datetime(2023, 1, 1, 12, 0, 0)
        lookup = FileLookup(current_cycle, num_levels=13, member=member)
        file_dict = lookup._gefs_file_info()

        # Verify member appears in file paths
        for files in file_dict.values():
            for file_path in files:
                assert f"ge{member}" in file_path

    def test_current_cycle_m6h_calculation(self):
        """Test that current_cycle_m6h is calculated correctly."""
        current_cycle = datetime(2023, 1, 1, 18, 0, 0)
        lookup = FileLookup(current_cycle, num_levels=13, member=None)

        expected_m6h = datetime(2023, 1, 1, 12, 0, 0)
        assert lookup.current_cycle_m6h == expected_m6h

    def test_file_info_delegation_gfs(self):
        """Test that get_file_info correctly delegates to GFS method."""
        current_cycle = datetime(2023, 1, 1, 12, 0, 0)
        lookup = FileLookup(current_cycle, num_levels=13, member=None)

        gfs_result = lookup._gfs_file_info()
        delegated_result = lookup.get_file_info()

        assert gfs_result == delegated_result

    def test_file_info_delegation_gefs(self):
        """Test that get_file_info correctly delegates to GEFS method."""
        current_cycle = datetime(2023, 1, 1, 12, 0, 0)
        lookup = FileLookup(current_cycle, num_levels=13, member="c00")

        gefs_result = lookup._gefs_file_info()
        delegated_result = lookup.get_file_info()

        assert gefs_result == delegated_result

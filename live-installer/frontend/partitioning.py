# coding: utf-8
#
import parted
from frontend import *

gettext.install("live-installer", "/usr/share/locale")

# Used as a decorator to run things in the main loop, from another thread


(IDX_PART_PATH,
 IDX_PART_TYPE,
 IDX_PART_DESCRIPTION,
 IDX_PART_FORMAT_AS,
 IDX_PART_MOUNT_AS,
 IDX_PART_SIZE,
 IDX_PART_FREE_SPACE,
 IDX_PART_OBJECT,
 IDX_PART_DISK) = list(range(9))


TMP_MOUNTPOINT = '/tmp/live-installer/tmpmount'
RESOURCE_DIR = './resources/'

EFI_MOUNT_POINT = '/boot/efi'
SWAP_MOUNT_POINT = 'swap'


def get_disks():
    disks = []
    exclude_devices = ['/dev/sr0', '/dev/sr1',
                       '/dev/cdrom', '/dev/dvd', '/dev/fd0', '/dev/nullb0']
    live_device = subprocess.getoutput(
        "findmnt -n -o source /run/live/medium").split('\n')[0]
    # remove partition numbers if any
    live_device = re.sub('[0-9]+$', '', live_device)
    if live_device is not None and live_device.startswith('/dev/'):
        exclude_devices.append(live_device)
        log("Excluding %s (detected as the live device)" % live_device)
    lsblk = shell_exec(
        'LC_ALL=en_US.UTF-8 lsblk -rindo TYPE,NAME,RM,SIZE,MODEL | sort -k3,2')
    for line in lsblk.stdout:
        try:
            elements = str(line).strip().split(" ")
            if len(elements) < 4:
                log("Can't parse blkid output: %s" % elements)
                continue
            elif len(elements) < 5:
                log("Can't find model in blkid output: %s" % elements)
                typevar, device, removable, size, model = elements[
                    0], elements[1], elements[2], elements[3], elements[1]
            else:
                typevar, device, removable, size, model = elements
            device = "/dev/" + device
            if str(typevar) == "b'disk" and device not in exclude_devices:
                # convert size to manufacturer's size for show, e.g. in GB, not
                # GiB!
                unit_index = 'BKMGTPEZY'.index(size.upper()[-1])
                l10n_unit = [_('B'), _('kB'), _('MB'), _('GB'), _(
                    'TB'), 'PB', 'EB', 'ZB', 'YB'][unit_index]
                size = "%s %s" % (
                    str(int(float(size[:-1]) * (1024 / 1000)**unit_index)), l10n_unit)
                model = model.replace("\\x20", " ")
                description = ('{} ({})'.format(
                    model.strip(), size)).replace("\\n'", "")
                if int(removable):
                    description = _('Removable:') + ' ' + description
                disks.append((device, description))
        except Exception as detail:
            log("Could not parse blkid output: %s (%s)" % (line, detail))
    return disks


def get_partitions():
    partitions = []
    for disk in get_disks():
        i = 1
        while os.path.exists("{}{}".format(disk[0], str(i))):
            partitions.append("{}{}".format(disk[0], str(i)))
            i += 1
    return partitions


def find_mbr(part):
    for disk in get_disks():
        i = 1
        while os.path.exists("{}{}".format(disk[0], str(i))):
            if part == "{}{}".format(disk[0], str(i)):
                return disk[0]
            i += 1
    return ""


def build_partitions(_installer):
    global installer
    installer = _installer
    installer.window.get_window().set_cursor(
        Gdk.Cursor.new(Gdk.CursorType.WATCH))  # "busy" cursor
    installer.window.set_sensitive(False)
    log("Starting PartitionSetup()")
    partition_setup = PartitionSetup()
    log("Finished PartitionSetup()")
    if partition_setup.disks:
        installer._selected_disk = partition_setup.disks[0][0]
    log("Showing the partition screen")
    installer.builder.get_object("treeview_disks").set_model(partition_setup)
    installer.builder.get_object("treeview_disks").expand_all()
    installer.window.get_window().set_cursor(None)
    installer.window.set_sensitive(True)


def edit_partition_dialog(widget, path, viewcol):
    ''' assign the partition ... '''
    model, itervar = installer.builder.get_object(
        "treeview_disks").get_selection().get_selected()
    if not itervar:
        return
    row = model[itervar]
    partition = row[IDX_PART_OBJECT]
    if (partition.partition.type != parted.PARTITION_EXTENDED and
            partition.partition.number != -1):
        dlg = PartitionDialog(row[IDX_PART_PATH],
                              row[IDX_PART_MOUNT_AS],
                              row[IDX_PART_FORMAT_AS],
                              row[IDX_PART_TYPE])
        response_is_ok, mount_as, format_as = dlg.show()
        if response_is_ok:
            assign_mount_point(partition, mount_as, format_as)


def assign_mount_point(partition, mount_point, filesystem):
    # Assign it in the treeview
    model = installer.builder.get_object("treeview_disks").get_model()
    for disk in model:
        for part in disk.iterchildren():
            if partition == part[IDX_PART_OBJECT]:
                part[IDX_PART_MOUNT_AS] = mount_point
                part[IDX_PART_FORMAT_AS] = filesystem
            elif mount_point == part[IDX_PART_MOUNT_AS]:
                part[IDX_PART_MOUNT_AS] = ""
                part[IDX_PART_FORMAT_AS] = ""
    # Assign it in our setup
    for part in installer.setup.partitions:
        if part == partition:
            partition.mount_as, partition.format_as = mount_point, filesystem
        elif part.mount_as == mount_point:
            part.mount_as, part.format_as = '', ''



def partitions_popup_menu(widget, event):
    if event.button != 3:
        return
    model, itervar = installer.builder.get_object(
        "treeview_disks").get_selection().get_selected()
    if not itervar:
        return
    partition = model.get_value(itervar, IDX_PART_OBJECT)
    if not partition:
        return
    partition_type = model.get_value(itervar, IDX_PART_TYPE)
    if (partition.partition.type == parted.PARTITION_EXTENDED or
        partition.partition.number == -1 or
            "swap" in partition_type):
        return
    menu = Gtk.Menu()
    menuItem = Gtk.MenuItem(_("Edit"))
    menuItem.connect("activate", edit_partition_dialog, None, None)
    menu.append(menuItem)
    menuItem = Gtk.SeparatorMenuItem()
    menu.append(menuItem)
    menuItem = Gtk.MenuItem(_("Assign to %s") % "/")
    menuItem.connect("activate", lambda w: assign_mount_point(
        partition, '/', 'ext4'))
    menu.append(menuItem)
    menuItem = Gtk.MenuItem(_("Assign to %s") % "swap")
    menuItem.connect("activate", lambda w: assign_mount_point(
        partition, 'swap', ''))
    menu.append(menuItem)
    for i in config.distro["additional_mountpoints"]:
        def menu_event(w,i=i):
            assign_mount_point(partition, i, 'ext4')
        menuItem = Gtk.MenuItem(_("Assign to %s") % i)
        menuItem.connect("activate", menu_event)
        menu.append(menuItem)
    if is_efi_supported():
        menuItem = Gtk.SeparatorMenuItem()
        menu.append(menuItem)
        for i in config.distro["additional_efi_mountpoints"]:
            def menu_event(w,i=i):
                assign_mount_point(partition, i, 'vfat')
        menuItem = Gtk.MenuItem(_("Assign to %s") % i)
        menuItem.connect("activate", menu_event)
        menu.append(menuItem)
    menu.show_all()
    menu.popup(None, None, None, None, 0, event.time)


def manually_edit_partitions(widget):
    """ Edit only known disks, selected one first """
    model, itervar = installer.builder.get_object(
        "treeview_disks").get_selection().get_selected()
    # prefer disk currently selected and show it first
    preferred = model[itervar][-1] if itervar else ''
    disks = ' '.join(sorted((disk for disk, desc in model.disks),
                            key=lambda disk: disk != preferred))
    os.system('umount -f ' + disks)
    os.system('{} {} &'.format(config.get(
        "partition_editor", "gparted"), disks))


def build_grub_partitions():
    grub_model = Gtk.ListStore(str)
    try:
        preferred = [
            p.partition.disk.device.path for p in installer.setup.partitions if p.mount_as == '/'][0]
    except IndexError:
        preferred = ''
    devices = sorted(list(d[0] for d in installer.setup.partition_setup.disks) +
                     list(
                         [_f for _f in (p.name for p in installer.setup.partitions) if _f]),
                     key=lambda path: path != preferred)
    for p in devices:
        grub_model.append([p])
    installer.builder.get_object("combobox_grub").set_model(grub_model)
    installer.builder.get_object("combobox_grub").set_active(0)


class PartitionSetup(Gtk.TreeStore):
    def __init__(self):
        super(PartitionSetup, self).__init__(str,  # path
                                             str,  # type (fs)
                                             str,  # description (OS)
                                             str,  # format to
                                             str,  # mount point
                                             str,  # size
                                             str,  # free space
                                             object,  # partition object
                                             str)  # disk device path
        installer.setup.partitions = []
        installer.setup.partition_setup = self

        os.popen('mkdir -p ' + TMP_MOUNTPOINT)
        self.disks = get_disks()
        log('Disks: ', self.disks)
        already_done_full_disk_format = False
        for disk_path, disk_description in self.disks:
            log("    Analyzing path='%s' description='%s'" %
                (disk_path, disk_description))
            try:
                disk_device = parted.getDevice(disk_path)
                disk = parted.Disk(disk_device)
            except Exception as detail:
                log("Found an issue while looking for the disk: %s" % detail)
                from frontend.gtk_interface import QuestionDialog
                dialog = QuestionDialog(_("Installation Tool"),
                                        _("No partition table was found on the hard drive: %s. Do you want the installer to create a set of partitions for you? Note: This will ERASE ALL DATA present on this disk.") % disk_description,
                                        None, installer.window)
                if not dialog:
                    continue  # the user said No, skip this disk
                try:
                    installer.window.get_window().set_cursor(Gdk.Cursor.new(Gdk.CursorType.WATCH))
                    if not already_done_full_disk_format:
                        assign_mount_format = full_disk_format(disk_device)
                        already_done_full_disk_format = True
                    else:
                        # Format but don't assign mount points
                        full_disk_format(disk_device)
                    installer.window.get_window().set_cursor(None)
                    disk = parted.Disk(disk_device)
                except Exception:
                    installer.window.get_window().set_cursor(None)
                    continue  # Something is wrong with this disk, skip it

            disk_iter = self.append(
                None, (disk_description, '', '', '', '', '', '', None, disk_path))
            free_space_partition = disk.getFreeSpacePartitions()
            primary_partitions = disk.getPrimaryPartitions()
            logical_partitions = disk.getLogicalPartitions()
            raid_partitions = disk.getRaidPartitions()
            lvm_partitions = disk.getLVMPartitions()
            partition_set = tuple(free_space_partition + primary_partitions +
                                  logical_partitions + raid_partitions + lvm_partitions)
            partitions = []
            for partition in partition_set:
                part = Partition(partition)
                log("{} {}".format(partition.path.replace("-", ""), part.size))
                # skip ranges <5MB
                if part.raw_size > 5242880:
                    partitions.append(part)
            # partitions = sorted(
            #    partitions, key=lambda part: part.partition.geometry.start)

            try:  # assign mount_as and format_as if disk was just auto-formatted
                for partition, (mount_as, format_as) in zip(
                        partitions, assign_mount_format):
                    partition.mount_as = mount_as
                    partition.format_as = format_as
                del assign_mount_format
            except NameError:
                pass
            # Needed to fix the 1% minimum Partition.size_percent
            # .5 for good measure
            sum_size_percent = sum(p.size_percent for p in partitions) + .5
            for partition in partitions:
                partition.size_percent = round(
                    partition.size_percent / sum_size_percent * 100, 1)
                installer.setup.partitions.append(partition)
                if partition.type != _('Free space'):
                    self.append(disk_iter, (partition.name,
                                            '<span>{}</span>'.format(
                                                partition.type),
                                            partition.description,
                                            partition.format_as,
                                            partition.mount_as,
                                            partition.size,
                                            partition.free_space,
                                            partition,
                                            disk_path))


@idle
def show_error(message):
    from frontend.gtk_interface import ErrorDialog
    ErrorDialog(_("Installer"), message)


def full_disk_format(device, create_boot=False, create_swap=False):
    # Create a default partition set up
    disk_label = ('gpt' if device.getLength('B') > 2**32 * .9 * device.sectorSize  # size of disk > ~2TB
                  or is_efi_supported()
                  else 'msdos')
    # Force lazy umount
    os.system("umount -lf {}*".format(device.path))
    # Wipe first 512 byte
    open(device.path, "w").write("\x00" * 512)
    return_code = os.system("parted -s %s mklabel %s" %
                            (device.path, disk_label))
    if return_code != 0:
        show_error(
            _("The partition table couldn't be written for %s. Restart the computer and try again.") % device.path)
        Gtk.main_quit()
        sys.exit(1)

    mkpart = (
        # (condition, mount_as, format_as, mkfs command, size_mb)
        # EFI
        (is_efi_supported(), EFI_MOUNT_POINT,
         'vfat', 'mkfs.vfat {} -F 32 ', 300),
        # boot
        (create_boot, '/boot', 'ext4', 'mkfs.ext4 -F {}', 1024),
        # swap - equal to RAM for hibernate to work well (but capped at ~8GB)
        (create_swap, SWAP_MOUNT_POINT, 'swap', 'mkswap {}', min(8800, int(round(
            1.1 / 1024 * int(getoutput("awk '/^MemTotal/{ print $2 }' /proc/meminfo")), -2)))),
        # root
        (True, '/', 'ext4', 'mkfs.ext4 -F {}', 0),
    )
    def run_parted(cmd): return os.system(
        'parted --script --align optimal {} {} ; sync'.format(device.path, cmd))
    start_mb = 2
    partition_number = 0
    partition_prefix = ""
    if device.path.startswith("/dev/nvme"):
        partition_prefix = "p"
    for partition in mkpart:
        log(partition)
        if partition[0]:
            partition_number = partition_number + 1
            mkfs = partition[3]
            size_mb = partition[4]
            end = '{}MB'.format(start_mb + size_mb) if size_mb else '100%'
            mkpart_cmd = 'mkpart primary {}MB {}'.format(start_mb, end)
            log("Executing: " + mkpart_cmd)
            run_parted(mkpart_cmd)
            partition_path = "%s%s%d" % (
                device.path, partition_prefix, partition_number)
            num_tries = 0
            while True:
                if os.path.exists(partition_path):
                    break
                if num_tries < 5:
                    num_tries += 1
                    err(("Could not find %s, waiting 1s..." % partition_path))
                    os.system("sync")
                    time.sleep(1)
                else:
                    show_error(
                        _("The partition %s could not be created. The installation will stop. Restart the computer and try again.") % partition_path)
                    Gtk.main_quit()
                    sys.exit(1)
            mkfs = mkfs.format(partition_path)
            log("Executing: " + mkfs)
            os.system(mkfs)
            start_mb += size_mb + 1
    if is_efi_supported():
        run_parted('set 1 boot on')
    return ((i[1], i[2]) for i in mkpart if i[0])


def to_human_readable(size):
    for unit in [' ', _('kB'), _('MB'), _(
            'GB'), _('TB'), 'PB', 'EB', 'ZB', 'YB']:
        if size < 1000:
            return "{:.1f} {}".format(size, unit)
        size /= 1000


class PartitionBase(object):
    # Partition object but only struct
    def __init__(self):
        self.format_as = ''
        self.mount_as = ''
        self.type = ''
        self.path = ''


class Partition(object):
    format_as = ''
    mount_as = ''

    def __init__(self, partition):
        assert partition.type not in (
            parted.PARTITION_METADATA, parted.PARTITION_EXTENDED)
        self.path = str(partition.path).replace(
            "-", "")  # /dev/sda-1 to /dev/sda1

        self.partition = partition
        self.length = partition.getLength()
        self.size_percent = max(
            1, round(80 * self.length / partition.disk.device.getLength(), 1))
        self.size = to_human_readable(partition.getLength('B'))
        self.raw_size = partition.getLength('B')
        # if not normal partition with /dev/sdXN path, set its name to '' and
        # discard it from model
        self.name = self.path if partition.number != -1 else ''
        self.mount_point = None
        self.description = ""
        try:
            self.type = partition.fileSystem.type
            # normalize fs variations (parted.filesystem.fileSystemType.keys())
            for fs in ('swap', 'hfs', 'ufs'):
                if fs in self.type:
                    self.type = fs
            self.style = self.type
        except AttributeError:  # non-formatted partitions
            self.type = {
                parted.PARTITION_LVM: 'LVM',
                parted.PARTITION_SWAP: 'swap',
                # Empty space on Extended partition is recognized as this
                parted.PARTITION_RAID: 'RAID',
                parted.PARTITION_PALO: 'PALO',
                parted.PARTITION_PREP: 'PReP',
                parted.PARTITION_LOGICAL: _('Logical partition'),
                parted.PARTITION_EXTENDED: _('Extended partition'),
                parted.PARTITION_FREESPACE: _('Free space'),
                parted.PARTITION_HPSERVICE: 'HP Service',
                parted.PARTITION_MSFT_RESERVED: 'MSFT Reserved',
            }.get(partition.type, _('Unknown'))
            self.style = {
                parted.PARTITION_SWAP: 'swap',
                parted.PARTITION_FREESPACE: 'freespace',
            }.get(partition.type, '')
        if "swap" in self.type:
            self.mount_as = SWAP_MOUNT_POINT

        # identify partition's description and used space
        try:
            os.system('mount --read-only {} {}'.format(self.path, TMP_MOUNTPOINT))
            df = getoutput("df {0} | grep '^{0}' | awk '{{print $2,$4,$5,$6}}' | tail -1".format(
                self.path)).decode("utf-8").split(" ")
            size = df[0]
            free = df[1]
            self.used_percent = df[2]
            self.mount_point = df[3]
            self.raw_size = int(size) * 1024
            log("size %s, free %s, self.used_percent %s, mount_point %s" % (
                size, free, self.used_percent, self.mount_point))

            self.size = to_human_readable(int(size) * 1024)
            # df returns values in 1024B-blocks by default
            self.free_space = to_human_readable(int(free) * 1024)
            self.used_percent = self.used_percent.replace("%", "") or 0
        except:
            self.description = ""
            if "swap" in self.type:
                self.os_fs_info, self.description, self.free_space, self.used_percent = ': ' + \
                    self.type, 'swap', '', 0
            else:
                self.os_fs_info, self.description, self.free_space, self.used_percent = ': ' + \
                    self.type, '', '', 0
        # for mountable partitions, more accurate than the getLength size
        # above
        self.description = ""
        if not self.mount_point:
            self.mount_point = TMP_MOUNTPOINT
        if path_exists(str(self.mount_point), str('etc/os-release')):
            self.description = getoutput("cat %s/etc/os-release | grep ^NAME=" % self.mount_point).decode("utf-8").replace(
                'NAME=', '').replace('"', '').strip()
        elif path_exists(str(self.mount_point), str('Windows/servicing/Version')):
            self.description = 'Windows ' + {
                '10.': '10',
                '6.4': '10',
                '6.3': '8.1',
                '6.2': '8',
                '6.1': '7',
                '6.0': 'Vista',
                '5.2': 'XP Pro x64',
                '5.1': 'XP',
                '5.0': '2000',
                '4.9': 'ME',
                '4.1': '98',
                '4.0': '95',
            }.get(getoutput('ls {}/Windows/servicing/Version'.format(self.mount_point))[:3].decode("utf-8"), '')
        elif path_exists(self.mount_point, 'Boot/BCD'):
            self.description = 'Windows ' + _('bootloader/recovery')
        elif path_exists(self.mount_point, 'Windows/System32'):
            self.description = 'Windows'
        elif path_exists(self.mount_point, 'System/Library/CoreServices/SystemVersion.plist'):
            self.description = 'Mac OS X'
        elif path_exists(self.mount_point, 'etc/'):
            self.description = 'Linux/Unix'
        else:
            try:
                if partition.active:
                    for flag in partition.getFlagsAsString().split(", "):
                        if flag in ["boot", "esp"] and self.type == "fat32":
                            self.description = _('EFI System Partition')
                            break
            except Exception as detail:
                # best effort
                err("Could not read partition flags for %s: %s" %
                    (self.path, detail))
        self.os_fs_info = ': {0.description} ({0.type}; {0.size}; {0.free_space})'.format(
            self) if self.description else ': ' + self.type
        log("                  . self.description %s self.os_fs_info %s" % (
            self.description, self.os_fs_info))
        os.system('umount ' + TMP_MOUNTPOINT + ' 2>/dev/null')

    def print_partition(self):
        log("Device: %s, format as: %s, mount as: %s" %
            (self.path, self.format_as, self.mount_as))


class PartitionDialog(object):
    def __init__(self, path, mount_as, format_as, typevar):
        glade_file = RESOURCE_DIR + 'interface.ui'
        self.builder = Gtk.Builder()
        self.builder.add_from_file(glade_file)
        self.window = self.builder.get_object("dialog")
        self.window.set_title(_("Edit partition"))
        self.builder.get_object("label_partition").set_markup(
            "<b>%s</b>" % _("Device:"))
        self.builder.get_object("label_partition_value").set_label(path)
        self.builder.get_object("label_use_as").set_markup(_("Format as:"))
        self.builder.get_object(
            "label_mount_point").set_markup(_("Mount point:"))
        self.builder.get_object("button_cancel").set_label(_("Cancel"))
        self.builder.get_object("button_ok").set_label(_("OK"))
        # Build supported filesystems list
        filesystems = ['', 'swap', 'none']
        for path in ["/bin", "/sbin", "/usr/bin", "/usr/sbin"]:
            for fs in getoutput('echo %s/mkfs.*' % path).split():
                fsname = str(fs).split("mkfs.")[1].replace("'", "")
                if fsname not in filesystems and "*" not in fsname:
                    filesystems.append(fsname)
        filesystems = sorted(set(filesystems))
        filesystems = sorted(filesystems, key=lambda x: 0 if x in (
            '', 'ext4') else 1 if x == 'swap' else 2)
        model = Gtk.ListStore(str)
        for i in filesystems:
            model.append([i])
        self.builder.get_object("combobox_use_as").set_model(model)
        self.builder.get_object("combobox_use_as").set_active(
            filesystems.index(format_as))
        # Build list of pre-provided mountpoints
        combobox = self.builder.get_object("comboboxentry_mount_point")
        model = Gtk.ListStore(str, str)
        model.append(["", "/"])
        model.append(["", "swap"])
        for i in config.distro["additional_mountpoints"]:
            model.append(["", i])
        if is_efi_supported():
            for i in config.distro["additional_efi_mountpoints"]:
                model.append(["", i])
        combobox.set_model(model)
        combobox.set_entry_text_column(1)
        combobox.set_id_column(1)
        combobox.get_child().set_text(mount_as)

    def show(self):
        response = self.window.run()
        w = self.builder.get_object("comboboxentry_mount_point")
        mount_as = w.get_child().get_text().strip()
        w = self.builder.get_object("combobox_use_as")
        format_as = w.get_model()[w.get_active()][0]
        self.window.destroy()
        if response in (Gtk.ResponseType.YES, Gtk.ResponseType.APPLY,
                        Gtk.ResponseType.OK, Gtk.ResponseType.ACCEPT):
            response_is_ok = True
        else:
            response_is_ok = False
        return response_is_ok, mount_as, format_as
